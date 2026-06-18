"""v0.7.2 模型 vs 赔率对比服务.

设计要点:
1. **3 模型注册表**: blend(默认) / elo / glicko2
2. **3 价值档位**: strong(>10%) / edge(5-10%) / none(<5%)
3. **批量优化**: 一次 DB 会话拉完所有 match + 评级,避免 N+1
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Match, MatchOdds
from app.services.elo import predict_match, predict_match_blend, HOME_BONUS
from app.services import glicko2 as g2_service
from app.services.odds_service import compute_market_probabilities, value_bet
from app.config import settings


def _value_tier(rate: float, threshold: float) -> str:
    """value_bet 率 → 价值档位."""
    if rate > 0.10:
        return "strong"
    if rate > threshold:
        return "edge"
    return "none"


def predict_match_with_model(
    db: Session, match_id: int, model: str
) -> Optional[Tuple[float, float, float]]:
    """调用对应模型预测,返回 (home_prob, draw_prob, away_prob).

    Returns None if 模型无该队数据或比赛不存在。
    """
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        return None
    home_code = m.home_team.fifa_code if m.home_team else None
    away_code = m.away_team.fifa_code if m.away_team else None
    if not home_code or not away_code:
        return None

    home_code_u = home_code.upper()
    away_code_u = away_code.upper()

    # 各模型签名/返回结构不同,显式分发,避免把 Session 错当 source 传入
    if model == "blend":
        result = predict_match_blend(home_code_u, away_code_u)
        if result.get("error") or result.get("blended") is None:
            return None
        probs = result["blended"]["probabilities"]

    elif model == "elo":
        result = predict_match(home_code_u, away_code_u)
        if result.get("error") or result.get("probabilities") is None:
            return None
        probs = result["probabilities"]

    elif model == "glicko2":
        rh = g2_service.lookup_glicko2_rating(home_code_u)
        ra = g2_service.lookup_glicko2_rating(away_code_u)
        if rh is None or ra is None:
            return None
        g2_pred = g2_service.predict_outcome(
            rh["rating"], rh["rd"],
            ra["rating"], ra["rd"],
            home_bonus=HOME_BONUS,
        )
        probs = {
            "home_win": g2_pred["win_a"],
            "draw": g2_pred["draw"],
            "away_win": g2_pred["win_b"],
        }

    else:
        return None

    return (
        float(probs.get("home_win", 0.0)),
        float(probs.get("draw", 0.0)),
        float(probs.get("away_win", 0.0)),
    )


def compare_match_odds(
    db: Session,
    match_id: int,
    model: str = "blend",
    bookmaker: Optional[str] = None,
) -> Optional[Dict]:
    """单场比赛:模型 vs 赔率对比.

    Returns: {
        match_id, model, bookmaker,
        model_probs: {home, draw, away},
        market_probs: {home, draw, away, total_vig},
        value_bet: {home, draw, away},
        best_value: {outcome, rate, tier} or None,
        odds: {home_win, draw, away_win, ...},
    } 或 None(无赔率或无模型)
    """
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        return None

    odds_row = (
        db.query(MatchOdds)
        .filter(MatchOdds.match_id == match_id)
        .filter(MatchOdds.bookmaker == bookmaker if bookmaker else MatchOdds.bookmaker == settings.odds_default_bookmaker)
        .order_by(MatchOdds.fetched_at.desc())
        .first()
    )
    if not odds_row:
        return None

    probs = predict_match_with_model(db, match_id, model)
    if probs is None:
        return None
    model_home, model_draw, model_away = probs

    market = compute_market_probabilities(
        odds_row.home_win, odds_row.draw, odds_row.away_win,
    )

    vb_home = value_bet(model_home, market["home_prob"])
    vb_draw = value_bet(model_draw, market["draw_prob"])
    vb_away = value_bet(model_away, market["away_prob"])

    candidates = {"home": vb_home, "draw": vb_draw, "away": vb_away}
    best_outcome, best_rate = max(candidates.items(), key=lambda kv: kv[1])
    if best_rate <= 0:
        best_value = None
    else:
        best_value = {
            "outcome": best_outcome,
            "rate": round(best_rate, 4),
            "tier": _value_tier(best_rate, settings.odds_value_bet_threshold),
        }

    return {
        "match_id": match_id,
        "home_team_code": m.home_team.fifa_code if m.home_team else None,
        "away_team_code": m.away_team.fifa_code if m.away_team else None,
        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
        "model": model,
        "bookmaker": odds_row.bookmaker,
        "odds": {
            "home_win": odds_row.home_win,
            "draw": odds_row.draw,
            "away_win": odds_row.away_win,
            "over_2_5": odds_row.over_2_5,
            "under_2_5": odds_row.under_2_5,
            "fetched_at": odds_row.fetched_at.isoformat() if odds_row.fetched_at else None,
        },
        "model_probs": {
            "home": round(model_home, 4),
            "draw": round(model_draw, 4),
            "away": round(model_away, 4),
        },
        "market_probs": {k: round(v, 4) for k, v in market.items()},
        "value_bet": {
            "home": round(vb_home, 4),
            "draw": round(vb_draw, 4),
            "away": round(vb_away, 4),
        },
        "best_value": best_value,
    }


def find_value_bets(
    db: Session,
    model: str = "blend",
    min_tier: str = "edge",
    limit: int = 20,
) -> List[Dict]:
    """扫描所有有赔率的未完赛比赛,找出价值投注.

    Args:
        model: 模型名 (blend/elo/glicko2)
        min_tier: 最低档位 (strong/edge/none),edge 表示 >= 5%
        limit: 返回 top N
    """
    from app.models import MatchOdds  # 避免循环 import

    tier_rank = {"none": 0, "edge": 1, "strong": 2}
    cutoff = tier_rank.get(min_tier, 1)

    # 一次拉完未完赛比赛及其默认盘口赔率
    rows = (
        db.query(Match, MatchOdds)
        .join(MatchOdds, MatchOdds.match_id == Match.id)
        .filter(Match.status.in_(["scheduled", "live"]))
        .filter(MatchOdds.bookmaker == settings.odds_default_bookmaker)
        .order_by(Match.kickoff_at.asc())
        .all()
    )

    results: List[Dict] = []
    for match, odds in rows:
        probs = predict_match_with_model(db, match.id, model)
        if probs is None:
            continue
        model_home, model_draw, model_away = probs

        market = compute_market_probabilities(odds.home_win, odds.draw, odds.away_win)
        vb_home = value_bet(model_home, market["home_prob"])
        vb_draw = value_bet(model_draw, market["draw_prob"])
        vb_away = value_bet(model_away, market["away_prob"])

        candidates = {"home": vb_home, "draw": vb_draw, "away": vb_away}
        best_outcome, best_rate = max(candidates.items(), key=lambda kv: kv[1])
        if best_rate <= 0:
            continue
        tier = _value_tier(best_rate, settings.odds_value_bet_threshold)
        if tier_rank.get(tier, 0) < cutoff:
            continue

        results.append({
            "match_id": match.id,
            "home_team_code": match.home_team.fifa_code if match.home_team else None,
            "away_team_code": match.away_team.fifa_code if match.away_team else None,
            "kickoff_at": match.kickoff_at.isoformat() if match.kickoff_at else None,
            "model": model,
            "bookmaker": odds.bookmaker,
            "best_outcome": best_outcome,
            "best_rate": round(best_rate, 4),
            "tier": tier,
            "odds": {
                "home_win": odds.home_win,
                "draw": odds.draw,
                "away_win": odds.away_win,
            },
            "model_probs": {
                "home": round(model_home, 4),
                "draw": round(model_draw, 4),
                "away": round(model_away, 4),
            },
            "market_probs": {
                "home": round(market["home_prob"], 4),
                "draw": round(market["draw_prob"], 4),
                "away": round(market["away_prob"], 4),
                "total_vig": market["total_vig"],
            },
        })

    # 按 best_rate 降序
    results.sort(key=lambda r: r["best_rate"], reverse=True)
    return results[:limit]