"""Elo 评分 + 预测 API (M1).

Endpoints:
  GET /api/elo/ratings            - 48 队 Elo 评分（按降序）
  GET /api/elo/ratings/{fifa_code} - 单队 Elo
  GET /api/elo/predict/{home}/{away} - 1v1 预测 (M1 纯 Elo)
  GET /api/elo/predict-enhanced/{home}/{away} - 1v1 增强预测 (M2 Elo + form + h2h)
  GET /api/elo/top                - Top N
  GET /api/elo/backtest           - 4 年回测指标
"""
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Team, Match, H2HHistoricalMatch
from app.services.elo import (
    get_team_elo,
    predict_match,
    predict_match_enhanced,
    get_top_elo,
    get_backtest_metrics,
    compare_predictions,
    load_elo_ratings,
    FIFA_TO_HICRUBEN,
)

router = APIRouter()


def _query_h2h_for_boost(db: Session, home_code: str, away_code: str, lookback: int = 5) -> Dict:
    """简化版 H2H 查询：先查 2026 完赛，再回退 2018/2022 历史种子.

    Returns:
        {home_wins, away_wins, draws, sample, source}
        home_wins/away_wins/draws 按 home_code 视角归一
    """
    home_code = home_code.upper()
    away_code = away_code.upper()
    result = {"home_wins": 0, "away_wins": 0, "draws": 0, "sample": 0, "source": "none"}

    # 1) 2026 完赛（status=finished + 双队匹配）
    past = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .all()
    )
    matched = []
    for m in past:
        h_code = m.home_team.fifa_code if m.home_team else None
        a_code = m.away_team.fifa_code if m.away_team else None
        if (h_code == home_code and a_code == away_code) or (h_code == away_code and a_code == home_code):
            matched.append((h_code, a_code, m.home_score, m.away_score))
    matched.sort(key=lambda x: x[0])  # 稳定排序
    matched = matched[:lookback]

    if matched:
        for h_code, a_code, hg, ag in matched:
            if h_code == home_code:
                hh_score, ah_score = hg, ag
            else:
                hh_score, ah_score = ag, hg
            if hh_score > ah_score:
                result["home_wins"] += 1
            elif hh_score < ah_score:
                result["away_wins"] += 1
            else:
                result["draws"] += 1
        result["sample"] = len(matched)
        result["source"] = "current_2026"
        return result

    # 2) 2018/2022 历史种子
    hist = (
        db.query(H2HHistoricalMatch)
        .filter(
            ((H2HHistoricalMatch.home_fifa_code == home_code) & (H2HHistoricalMatch.away_fifa_code == away_code))
            | ((H2HHistoricalMatch.home_fifa_code == away_code) & (H2HHistoricalMatch.away_fifa_code == home_code))
        )
        .order_by(H2HHistoricalMatch.match_date.desc())
        .limit(lookback)
        .all()
    )
    if hist:
        for h in hist:
            if h.home_fifa_code == home_code:
                hh_score, ah_score = h.home_score, h.away_score
            else:
                hh_score, ah_score = h.away_score, h.home_score
            if hh_score > ah_score:
                result["home_wins"] += 1
            elif hh_score < ah_score:
                result["away_wins"] += 1
            else:
                result["draws"] += 1
        result["sample"] = len(hist)
        result["source"] = "history_2018_2022"
    return result


@router.get("/elo/predict-enhanced/{home_code}/{away_code}")
def predict_enhanced(
    home_code: str,
    away_code: str,
    source: str = Query("hicruben", description="Elo 数据源: hicruben 或 statsbomb"),
    db: Session = Depends(get_db),
) -> Dict:
    """M2 增强预测：Elo + form + H2H 加权.

    返回 v1 (纯 Elo) 和 v2 (增强) 双套结果用于对比。
    source 参数可切换底层 Elo 数据源（默认 hicruben）。
    """
    if source not in ("hicruben", "statsbomb"):
        raise HTTPException(status_code=400, detail="source 必须是 'hicruben' 或 'statsbomb'")
    home_code_u = home_code.upper()
    away_code_u = away_code.upper()

    # 查 form
    home_team = db.query(Team).filter(Team.fifa_code == home_code_u).first()
    away_team = db.query(Team).filter(Team.fifa_code == away_code_u).first()
    home_form = home_team.recent_form_points if home_team else None
    away_form = away_team.recent_form_points if away_team else None

    # 查 H2H
    h2h = _query_h2h_for_boost(db, home_code_u, away_code_u, lookback=5)

    result = predict_match_enhanced(
        home_code=home_code_u,
        away_code=away_code_u,
        home_form=home_form,
        away_form=away_form,
        h2h_home_wins=h2h["home_wins"],
        h2h_away_wins=h2h["away_wins"],
        h2h_draws=h2h["draws"],
        source=source,
    )
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@router.get("/elo/ratings", response_model=List[Dict])
def list_ratings(source: str = Query("hicruben", description="Elo 数据源: hicruben 或 statsbomb")) -> List[Dict]:
    """48 参赛队 Elo 评分（按 Elo 降序）."""
    if source not in ("hicruben", "statsbomb"):
        raise HTTPException(status_code=400, detail="source 必须是 'hicruben' 或 'statsbomb'")
    if source == "statsbomb":
        rows = get_top_elo(limit=200, source="statsbomb")
        return [{'fifa_code': r['fifa_code'], 'elo': r['elo'], 'rating_source': r['rating_source']} for r in rows]
    data = load_elo_ratings()
    ratings = data.get('ratings', {})
    rev_map = {v: k for k, v in FIFA_TO_HICRUBEN.items()}
    rows = []
    for kebab, elo in ratings.items():
        fifa_code = rev_map.get(kebab)
        if fifa_code:
            rows.append({
                'fifa_code': fifa_code,
                'elo': elo,
                'rating_source': 'hicruben',
            })
    rows.sort(key=lambda x: -x['elo'])
    return rows


@router.get("/elo/ratings/{fifa_code}")
def get_rating(fifa_code: str, source: str = Query("hicruben", description="Elo 数据源: hicruben 或 statsbomb")) -> Dict:
    """单队 Elo 评分."""
    if source not in ("hicruben", "statsbomb"):
        raise HTTPException(status_code=400, detail="source 必须是 'hicruben' 或 'statsbomb'")
    code = fifa_code.upper()
    if source == "statsbomb":
        from app.services.elo import _get_team_elo_with_source
        rating, rating_source, reason = _get_team_elo_with_source(code, source="statsbomb")
        if rating is None:
            raise HTTPException(status_code=404, detail=f"球队 {code} 不在 Elo 数据中")
        return {
            'fifa_code': code,
            'elo': rating,
            'rating_source': rating_source,
            'fallback_reason': reason,
        }
    elo = get_team_elo(code)
    if elo is None:
        raise HTTPException(status_code=404, detail=f"球队 {code} 不在 Elo 数据中")
    return {'fifa_code': code, 'elo': elo, 'rating_source': 'hicruben'}


@router.get("/elo/predict/{home_code}/{away_code}")
def predict(
    home_code: str,
    away_code: str,
    source: str = Query("hicruben", description="Elo 数据源: hicruben 或 statsbomb"),
) -> Dict:
    """预测单场比赛 1X2 + 期望进球."""
    if source not in ("hicruben", "statsbomb"):
        raise HTTPException(status_code=400, detail="source 必须是 'hicruben' 或 'statsbomb'")
    result = predict_match(home_code, away_code, source=source)
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@router.get("/elo/top")
def top_elo(
    limit: int = Query(10, ge=1, le=48),
    source: str = Query("hicruben", description="Elo 数据源: hicruben 或 statsbomb"),
) -> List[Dict]:
    """Top N Elo 评分榜."""
    if source not in ("hicruben", "statsbomb"):
        raise HTTPException(status_code=400, detail="source 必须是 'hicruben' 或 'statsbomb'")
    rows = get_top_elo(limit=limit, source=source)
    return [{'fifa_code': r['fifa_code'], 'elo': r['elo'], 'rating_source': r['rating_source']} for r in rows]


@router.get("/elo/compare/{home_code}/{away_code}")
def compare(home_code: str, away_code: str) -> Dict:
    """同时返回 Hicruben 和 StatsBomb 两套预测结果，用于对比."""
    return compare_predictions(home_code, away_code)


@router.get("/elo/backtest")
def backtest() -> Dict:
    """4 年回测指标（913 场 walk-forward）."""
    return get_backtest_metrics()
