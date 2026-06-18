"""v0.13.0+ MarketBlend: Elo + Glicko-2 + 市场赔率 三方加权融合.

设计要点:
  - 默认权重 0.4 / 0.3 / 0.3, 兼顾模型稳定性与市场信号
  - 无市场赔率时自动 fallback 到 Elo + Glicko-2 双模型融合
  - 保持与现有 /elo/predict-blend 端点一致的返回结构, 便于前端复用
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.models import Match, MatchOdds, Team
from app.services.elo import predict_match, predict_match_blend, HOME_BONUS
from app.services import glicko2 as g2_service
from app.services.odds_service import compute_market_probabilities


def _validate_weights(w_elo: float, w_glicko2: float, w_market: float) -> None:
    """校验三方权重之和为 1."""
    total = w_elo + w_glicko2 + w_market
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"w_elo + w_glicko2 + w_market 必须等于 1.0, 当前={total}")


def _glicko2_result(home_code: str, away_code: str) -> Optional[Dict]:
    """构造 Glicko-2 预测结果字典, 缺数据时返回 None."""
    rh = g2_service.lookup_glicko2_rating(home_code)
    ra = g2_service.lookup_glicko2_rating(away_code)
    if rh is None or ra is None:
        return None
    g2_pred = g2_service.predict_outcome(
        rh["rating"], rh["rd"],
        ra["rating"], ra["rd"],
        home_bonus=HOME_BONUS,
    )
    g2_data = g2_service.load_glicko2_ratings()
    return {
        "model": "glicko2_v1",
        "home": {"fifa_code": home_code, "rating": rh["rating"], "rd": rh["rd"], "volatility": rh["volatility"]},
        "away": {"fifa_code": away_code, "rating": ra["rating"], "rd": ra["rd"], "volatility": ra["volatility"]},
        "probabilities": {
            "home_win": g2_pred["win_a"],
            "draw": g2_pred["draw"],
            "away_win": g2_pred["win_b"],
        },
        "expected_score": g2_pred["expected_score"],
        "uncertainty": g2_pred["uncertainty"],
        "data_source": "hicruben/world-cup-2026-prediction-model (913 matches walk-forward)",
        "data_as_of": g2_data.get("generatedAt"),
    }


def _find_match_with_odds(
    db: Session,
    home_code: str,
    away_code: str,
    match_id: Optional[int] = None,
) -> Optional[Tuple[Match, MatchOdds]]:
    """按 match_id 或 home/away code 查找带默认盘口赔率的本地比赛."""
    if match_id is not None:
        m = db.query(Match).filter(Match.id == match_id).first()
        if not m:
            return None
        home_team = m.home_team
        away_team = m.away_team
        if home_team is None or away_team is None:
            return None
        if {home_team.fifa_code, away_team.fifa_code} != {home_code, away_code}:
            return None
        odds = (
            db.query(MatchOdds)
            .filter(MatchOdds.match_id == match_id)
            .filter(MatchOdds.bookmaker == settings.odds_default_bookmaker)
            .order_by(MatchOdds.fetched_at.desc())
            .first()
        )
        return (m, odds) if odds else None

    # 无 match_id: 找最近一场 home/away 对上且未完赛的比赛
    HomeTeam = aliased(Team)
    AwayTeam = aliased(Team)
    m = (
        db.query(Match)
        .join(HomeTeam, Match.home_team_id == HomeTeam.id)
        .join(AwayTeam, Match.away_team_id == AwayTeam.id)
        .filter(
            HomeTeam.fifa_code == home_code,
            AwayTeam.fifa_code == away_code,
            Match.status.in_(["scheduled", "live"]),
            Match.kickoff_at.isnot(None),
        )
        .order_by(Match.kickoff_at.asc())
        .first()
    )
    if not m:
        return None
    odds = (
        db.query(MatchOdds)
        .filter(MatchOdds.match_id == m.id)
        .filter(MatchOdds.bookmaker == settings.odds_default_bookmaker)
        .order_by(MatchOdds.fetched_at.desc())
        .first()
    )
    return (m, odds) if odds else None


def predict_market_blend(
    db: Session,
    home_code: str,
    away_code: str,
    match_id: Optional[int] = None,
    w_elo: float = 0.4,
    w_glicko2: float = 0.3,
    w_market: float = 0.3,
) -> Dict:
    """MarketBlend 三方融合预测.

    Args:
        db: SQLAlchemy Session
        home_code: 主队 FIFA code
        away_code: 客队 FIFA code
        match_id: 可选, 强制用某场比赛的赔率
        w_elo/w_glicko2/w_market: 三方权重, 默认 0.4/0.3/0.3

    Returns:
        {
            "home", "away", "match_id",
            "elo", "glicko2", "market",
            "blended": {"model", "weights", "probabilities"},
            "predicted_outcome", "confidence",
            "model_version", "fallback_reason", "error"
        }
    """
    _validate_weights(w_elo, w_glicko2, w_market)
    home_code_u = home_code.upper()
    away_code_u = away_code.upper()

    # 1) Elo
    elo_result = predict_match(home_code_u, away_code_u)
    if elo_result.get("error"):
        return {"error": elo_result["error"]}
    elo_probs = elo_result["probabilities"]

    # 2) Glicko-2
    g2_result = _glicko2_result(home_code_u, away_code_u)
    if g2_result is None:
        return {"error": f"球队 {home_code_u} 或 {away_code_u} 不在 Glicko-2 数据中"}
    g2_probs = g2_result["probabilities"]

    # 3) 市场赔率
    match_and_odds = _find_match_with_odds(db, home_code_u, away_code_u, match_id)

    # 4) 融合
    if match_and_odds is None:
        # fallback: 退化为 Elo + Glicko-2 双模型融合, 权重按原比例重归一化
        denom = w_elo + w_glicko2
        if denom <= 0:
            return {"error": "市场赔率不可用且 Elo/Glicko-2 权重均为 0"}
        fallback_blend = predict_match_blend(
            home_code_u, away_code_u,
            w_elo=w_elo / denom, w_glicko2=w_glicko2 / denom,
        )
        blended_probs = fallback_blend["blended"]["probabilities"]
        predicted = max(blended_probs, key=blended_probs.get)
        return {
            "home": elo_result["home"],
            "away": elo_result["away"],
            "match_id": None,
            "elo": {"model": elo_result["model"], "probabilities": elo_probs},
            "glicko2": g2_result,
            "market": None,
            "blended": {
                "model": "market_blend_fallback_v1",
                "weights": {
                    "elo": round(w_elo / denom, 4),
                    "glicko2": round(w_glicko2 / denom, 4),
                    "market": 0.0,
                },
                "probabilities": blended_probs,
            },
            "predicted_outcome": {"home_win": "H", "draw": "D", "away_win": "A"}[predicted],
            "confidence": blended_probs[predicted],
            "model_version": "v7c_market_blend_fallback",
            "fallback_reason": "market_odds_unavailable",
            "data_source": elo_result.get("data_source"),
            "data_as_of": elo_result.get("data_as_of"),
            "error": None,
        }

    match_obj, odds_row = match_and_odds
    market = compute_market_probabilities(odds_row.home_win, odds_row.draw, odds_row.away_win)
    market_probs = {
        "home_win": market["home_prob"],
        "draw": market["draw_prob"],
        "away_win": market["away_prob"],
    }

    blended_probs = {
        "home_win": round(
            w_elo * elo_probs["home_win"]
            + w_glicko2 * g2_probs["home_win"]
            + w_market * market_probs["home_win"],
            4,
        ),
        "draw": round(
            w_elo * elo_probs["draw"]
            + w_glicko2 * g2_probs["draw"]
            + w_market * market_probs["draw"],
            4,
        ),
        "away_win": round(
            w_elo * elo_probs["away_win"]
            + w_glicko2 * g2_probs["away_win"]
            + w_market * market_probs["away_win"],
            4,
        ),
    }
    predicted = max(blended_probs, key=blended_probs.get)

    return {
        "home": elo_result["home"],
        "away": elo_result["away"],
        "match_id": match_obj.id,
        "elo": {"model": elo_result["model"], "probabilities": elo_probs},
        "glicko2": g2_result,
        "market": {
            "bookmaker": odds_row.bookmaker,
            "odds": {
                "home_win": odds_row.home_win,
                "draw": odds_row.draw,
                "away_win": odds_row.away_win,
            },
            "probabilities": {
                "home_win": round(market_probs["home_win"], 4),
                "draw": round(market_probs["draw"], 4),
                "away_win": round(market_probs["away_win"], 4),
                "total_vig": market["total_vig"],
            },
            "fetched_at": odds_row.fetched_at.isoformat() if odds_row.fetched_at else None,
        },
        "blended": {
            "model": "market_blend_v1",
            "weights": {"elo": w_elo, "glicko2": w_glicko2, "market": w_market},
            "probabilities": blended_probs,
        },
        "predicted_outcome": {"home_win": "H", "draw": "D", "away_win": "A"}[predicted],
        "confidence": blended_probs[predicted],
        "model_version": "v7c_market_blend",
        "fallback_reason": None,
        "data_source": elo_result.get("data_source"),
        "data_as_of": elo_result.get("data_as_of"),
        "error": None,
    }
