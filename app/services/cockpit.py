"""Cockpit 总览聚合服务（v0.14.2）.

目标：为总览驾驶舱提供“统计 + 总预览 + 互联互通”的一站式数据，
避免前端重复调用多个详情页 API。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Match, Team
from app.services import data_source_health, simulator, sync_status
from app.services.elo import predict_match as elo_predict
from app.services.elo import predict_match_blend, HOME_BONUS
from app.services import glicko2 as g2_service

import time
from typing import Any, Dict


# 进程内缓存：Cockpit summary 计算重（MC 1000 sims + 外部源健康探测），缓存 5 分钟
_COCKPIT_CACHE: Dict[str, Any] = {}
_COCKPIT_CACHE_TTL_SECONDS = 300


THRESHOLD_QUALIFIED = 99.0
THRESHOLD_ELIMINATED = 1.0


def _all_matches_in_range_finished(db: Session, start: int, end: int) -> bool:
    """判断 match_number 区间内的比赛是否全部已结束（无记录视为未完成）."""
    matches = db.query(Match).filter(Match.match_number >= start, Match.match_number <= end).all()
    if not matches:
        return False
    return all(m.status == "finished" for m in matches)


def get_tournament_progress(db: Session) -> Dict:
    """赛事总体进度与淘汰赛里程碑."""
    total = db.query(Match).count()
    finished = db.query(Match).filter(Match.status == "finished").count()
    live = db.query(Match).filter(Match.status == "live").count()
    scheduled = db.query(Match).filter(Match.status == "scheduled").count()

    # 导入内部函数判断小组赛是否结束
    from app.services.bracket_logic import _group_stage_finished

    group_stage_finished = _group_stage_finished(db)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    in24h_end = now + timedelta(hours=24)

    today_matches = (
        db.query(Match)
        .filter(Match.kickoff_at >= today_start, Match.kickoff_at < today_end)
        .count()
    )
    in24h_matches = (
        db.query(Match)
        .filter(Match.kickoff_at >= now, Match.kickoff_at < in24h_end)
        .count()
    )

    finished_matches = db.query(Match).filter(Match.status == "finished").all()
    total_goals = sum(
        (m.home_score or 0) + (m.away_score or 0) for m in finished_matches
    )
    avg_goals = round(total_goals / len(finished_matches), 2) if finished_matches else 0.0

    return {
        "total_matches": total,
        "finished_matches": finished,
        "live_matches": live,
        "scheduled_matches": scheduled,
        "today_matches": today_matches,
        "in24h_matches": in24h_matches,
        "avg_goals": avg_goals,
        "completion_rate": round(finished / total * 100, 1) if total else 0.0,
        "group_stage_finished": group_stage_finished,
        "milestones": {
            "r32_locked": group_stage_finished,
            "r16_locked": _all_matches_in_range_finished(db, 73, 88),
            "qf_locked": _all_matches_in_range_finished(db, 89, 96),
            "sf_locked": _all_matches_in_range_finished(db, 97, 100),
            "final_locked": _all_matches_in_range_finished(db, 101, 102),
        },
    }


def get_qualification_summary(db: Session, advance_odds=None) -> Dict:
    """晋级/淘汰总览 + 最佳第 3 名竞争榜.

    基于 simulator.simulate_group_advancement 的蒙特卡洛概率。
    """
    odds = advance_odds if advance_odds is not None else simulator.simulate_group_advancement(db, n_sims=1000)
    if not odds:
        return {
            "qualified": 0,
            "eliminated": 0,
            "pending": 0,
            "direct_qualifiers": 0,
            "third_place_qualifiers": 0,
            "best_thirds": [],
        }

    qualified = [o for o in odds if o.advance_overall_prob >= THRESHOLD_QUALIFIED]
    eliminated = [o for o in odds if o.advance_overall_prob <= THRESHOLD_ELIMINATED]
    pending = [o for o in odds if THRESHOLD_ELIMINATED < o.advance_overall_prob < THRESHOLD_QUALIFIED]
    direct = [o for o in odds if o.direct_qualify_prob >= THRESHOLD_QUALIFIED]
    third = [o for o in odds if o.third_place_prob >= THRESHOLD_QUALIFIED]

    best_thirds = sorted(
        [o for o in odds if o.third_place_prob > 0],
        key=lambda x: (-x.third_place_prob, -x.points, -x.goal_diff, -x.goals_for),
    )[:10]

    def _team_dict(o):
        return {
            "team_id": o.team_id,
            "name_zh": o.team_name,
            "flag_emoji": o.flag_emoji,
            "group_name": o.group_name,
            "points": o.points,
            "goal_diff": o.goal_diff,
            "direct_prob": o.direct_qualify_prob,
            "third_prob": o.third_place_prob,
            "advance_prob": o.advance_overall_prob,
            "eliminated_prob": o.eliminated_prob,
        }

    return {
        "qualified": len(qualified),
        "eliminated": len(eliminated),
        "pending": len(pending),
        "direct_qualifiers": len(direct),
        "third_place_qualifiers": len(third),
        "best_thirds": [_team_dict(o) for o in best_thirds],
    }


def _match_prediction_summary(match: Match) -> Optional[Dict]:
    """计算单场比赛的 Elo / Glicko-2 / Blend 三模型预测摘要."""
    home = match.home_team
    away = match.away_team
    if not home or not away:
        return None
    home_code = (home.fifa_code or "").upper()
    away_code = (away.fifa_code or "").upper()
    if not home_code or not away_code:
        return None

    # Elo
    elo_result = elo_predict(home_code, away_code, source="hicruben")
    if elo_result.get("error"):
        elo_result = None

    # Glicko-2
    rh = g2_service.lookup_glicko2_rating(home_code)
    ra = g2_service.lookup_glicko2_rating(away_code)
    g2_result = None
    if rh and ra:
        g2_pred = g2_service.predict_outcome(
            rh["rating"], rh["rd"], ra["rating"], ra["rd"], home_bonus=HOME_BONUS,
        )
        g2_result = {
            "probabilities": {
                "home_win": g2_pred["win_a"],
                "draw": g2_pred["draw"],
                "away_win": g2_pred["win_b"],
            },
        }

    # Blend
    blend_result = predict_match_blend(home_code, away_code, w_elo=0.5, w_glicko2=0.5, source="hicruben")
    blend_probs = None
    if blend_result.get("blended"):
        blend_probs = blend_result["blended"]["probabilities"]

    # 共识概率 = 可用模型平均
    prob_lists = {"home_win": [], "draw": [], "away_win": []}
    for src in (elo_result, g2_result, {"probabilities": blend_probs} if blend_probs else None):
        if src and src.get("probabilities"):
            for k in prob_lists:
                prob_lists[k].append(src["probabilities"][k])
    consensus = {k: round(sum(v) / len(v), 4) if v else None for k, v in prob_lists.items()}

    # 模型分歧 = home_win 最大 - 最小
    prob_sources = []
    if elo_result and elo_result.get("probabilities"):
        prob_sources.append(elo_result["probabilities"])
    if g2_result and g2_result.get("probabilities"):
        prob_sources.append(g2_result["probabilities"])
    if blend_probs:
        prob_sources.append(blend_probs)
    home_probs = [p["home_win"] for p in prob_sources]
    disagreement = round(max(home_probs) - min(home_probs), 4) if len(home_probs) >= 2 else 0.0

    return {
        "home_code": home_code,
        "away_code": away_code,
        "elo": elo_result["probabilities"] if elo_result else None,
        "glicko2": g2_result["probabilities"] if g2_result else None,
        "blend": blend_probs,
        "consensus": consensus,
        "disagreement": disagreement,
    }


def _impact_label(match: Match, advance_map: Dict[int, float]) -> str:
    """根据出线概率给比赛打标签."""
    if match.stage != "小组赛":
        return "淘汰赛"
    home_prob = advance_map.get(match.home_team_id, 50.0)
    away_prob = advance_map.get(match.away_team_id, 50.0)

    if home_prob >= 95 and away_prob >= 95:
        return "头名之争"
    if (home_prob >= 95 and away_prob <= 50) or (away_prob >= 95 and home_prob <= 50):
        return "强弱对话"
    if home_prob <= 5 and away_prob <= 5:
        return "荣誉战"
    if 10 <= home_prob <= 60 and 10 <= away_prob <= 60:
        return "生死战"
    return "出线关键战"


def get_critical_matches(db: Session, hours: int = 72, limit: int = 8, advance_odds=None) -> List[Dict]:
    """未来 N 小时关键战，附带模型共识与出线影响标签."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)
    matches = (
        db.query(Match)
        .filter(Match.status != "finished")
        .filter(Match.kickoff_at >= now)
        .filter(Match.kickoff_at <= cutoff)
        .filter(Match.home_team_id.isnot(None))
        .filter(Match.away_team_id.isnot(None))
        .order_by(Match.kickoff_at)
        .limit(limit * 3)
        .all()
    )

    # 出线概率映射
    odds = advance_odds if advance_odds is not None else simulator.simulate_group_advancement(db, n_sims=1000)
    advance_map = {o.team_id: o.advance_overall_prob for o in odds}

    results: List[Dict] = []
    for m in matches:
        pred = _match_prediction_summary(m)
        if not pred:
            continue
        label = _impact_label(m, advance_map)
        results.append({
            "match_id": m.id,
            "match_number": m.match_number,
            "stage": m.stage,
            "group_name": m.group_name,
            "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
            "home_team": {
                "id": m.home_team_id,
                "name_zh": m.home_team.name_zh if m.home_team else "",
                "flag_emoji": m.home_team.flag_emoji if m.home_team else "",
                "fifa_code": m.home_team.fifa_code if m.home_team else "",
                "advance_prob": advance_map.get(m.home_team_id),
            },
            "away_team": {
                "id": m.away_team_id,
                "name_zh": m.away_team.name_zh if m.away_team else "",
                "flag_emoji": m.away_team.flag_emoji if m.away_team else "",
                "fifa_code": m.away_team.fifa_code if m.away_team else "",
                "advance_prob": advance_map.get(m.away_team_id),
            },
            "impact_label": label,
            "prediction": pred,
        })
        if len(results) >= limit:
            break
    return results


def get_model_consensus_highlights(critical_matches: List[Dict], n: int = 3) -> List[Dict]:
    """从关键战中挑选模型共识度最高、置信度最高的比赛."""
    valid = [m for m in critical_matches if m["prediction"]["consensus"]["home_win"] is not None]
    # 排序：分歧小优先，然后置信度高
    valid.sort(
        key=lambda m: (
            m["prediction"]["disagreement"],
            -max(m["prediction"]["consensus"].values()),
        )
    )
    return valid[:n]


def get_market_model_divergence(db: Session, limit: int = 5) -> List[Dict]:
    """市场 vs 模型偏离的价值投注（若无赔率数据则返回空）."""
    try:
        from app.services.model_odds_compare import find_value_bets
        rows = find_value_bets(db, model="blend", min_tier="edge", limit=limit)
    except Exception:  # noqa: BLE001
        return []

    results: List[Dict] = []
    for r in rows:
        outcome = r.get("best_outcome", "home")
        model_prob = r.get("model_probs", {}).get(outcome, 0)
        market_prob = r.get("market_probs", {}).get(outcome, 0)
        home_code = r.get("home_team_code") or ""
        away_code = r.get("away_team_code") or ""
        results.append({
            "match_id": r["match_id"],
            "home_team": {"fifa_code": home_code, "name_zh": home_code},
            "away_team": {"fifa_code": away_code, "name_zh": away_code},
            "best_outcome": outcome,
            "model_prob": model_prob,
            "market_prob": market_prob,
            "tier": r.get("tier", "none"),
        })
    return results


def get_elo_top_teams(db: Session, limit: int = 5) -> List[Dict]:
    """Elo 战力 Top N."""
    teams = (
        db.query(Team)
        .filter(Team.elo_rating.isnot(None))
        .order_by(Team.elo_rating.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "team_id": t.id,
            "fifa_code": t.fifa_code,
            "name_zh": t.name_zh,
            "flag_emoji": t.flag_emoji,
            "elo_rating": t.elo_rating,
            "group_name": t.group_name,
        }
        for t in teams
    ]


def get_data_health() -> Dict:
    """数据源健康 + sync 状态聚合."""
    return {
        "sources": data_source_health.get_health_summary(),
        "sync": sync_status.get_status(),
    }


def build_cockpit_summary(db: Session, use_cache: bool = True) -> Dict:
    """构建总览驾驶舱完整摘要.

    默认启用 5 分钟进程内缓存，避免每次请求都重算 MC 模拟 + 外部源探测。
    """
    now = time.time()
    if use_cache:
        cached = _COCKPIT_CACHE.get("summary")
        if cached and (now - cached.get("_cached_at", 0)) < _COCKPIT_CACHE_TTL_SECONDS:
            cached_copy = dict(cached)
            cached_copy["cached"] = True
            cached_copy["cache_age_seconds"] = round(now - cached_copy.pop("_cached_at"), 2)
            return cached_copy

    advance_odds = simulator.simulate_group_advancement(db, n_sims=1000)
    critical = get_critical_matches(db, advance_odds=advance_odds)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tournament_progress": get_tournament_progress(db),
        "qualification_summary": get_qualification_summary(db, advance_odds=advance_odds),
        "data_health": get_data_health(),
        "critical_matches": critical,
        "model_consensus": get_model_consensus_highlights(critical),
        "market_model_divergence": get_market_model_divergence(db),
        "elo_top_teams": get_elo_top_teams(db),
        "cached": False,
        "cache_age_seconds": 0,
    }

    # 写入缓存
    cache_entry = dict(summary)
    cache_entry["_cached_at"] = now
    _COCKPIT_CACHE["summary"] = cache_entry

    return summary
