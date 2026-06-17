"""Elo 评分 + 预测 API (M1 + M2 + Glicko-2 v0.6.0).

Endpoints:
  GET /api/elo/ratings            - 48 队 Elo 评分（按降序）
  GET /api/elo/ratings/{fifa_code} - 单队 Elo
  GET /api/elo/predict/{home}/{away} - 1v1 预测 (M1 纯 Elo)
  GET /api/elo/predict-enhanced/{home}/{away} - 1v1 增强预测 (M2 Elo + form + h2h)
  GET /api/elo/top                - Top N
  GET /api/elo/backtest           - 4 年回测指标
  GET /api/elo/predict-glicko2/{home}/{away} - 1v1 预测 (Glicko-2 v0.6.0+)
  GET /api/elo/glicko2-ratings    - Glicko-2 全队评分
"""
from typing import List, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Team, Match, H2HHistoricalMatch
from app.services.elo import (
    get_team_elo,
    predict_match,
    predict_match_enhanced,
    predict_match_blend,
    get_top_elo,
    get_backtest_metrics,
    compare_predictions,
    load_elo_ratings,
    FIFA_TO_HICRUBEN,
    HOME_BONUS,
)
from app.services import glicko2 as g2_service
from app.services.weight_sweep import run_weight_sweep

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
    match_id: Optional[int] = Query(None, description="比赛 ID (v0.6.0+ 用于自动记录 prediction_log)"),
    db: Session = Depends(get_db),
) -> Dict:
    """预测单场比赛 1X2 + 期望进球. v0.6.0+ 支持传 match_id 自动写 prediction_log."""
    if source not in ("hicruben", "statsbomb"):
        raise HTTPException(status_code=400, detail="source 必须是 'hicruben' 或 'statsbomb'")
    result = predict_match(home_code, away_code, source=source)
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])

    # v0.6.0: 自动写 prediction_log
    if match_id is not None:
        try:
            from app.services.prediction_log import record_prediction
            model_version = "v1_elo" if source == "hicruben" else "v1_elo_statsbomb"
            record_prediction(
                db=db,
                match_id=match_id,
                model_version=model_version,
                pred_home_win=result.get("probabilities", {}).get("home_win", 0),
                pred_draw=result.get("probabilities", {}).get("draw", 0),
                pred_away_win=result.get("probabilities", {}).get("away_win", 0),
                elo_home=result.get("home", {}).get("elo"),
                elo_away=result.get("away", {}).get("elo"),
                source=source,
            )
        except Exception as e:
            # 不影响主流程
            print(f"[prediction_log] 写入失败: {e}")

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


# === Glicko-2 (v0.6.0+) ===

@router.get("/elo/predict-glicko2/{home_code}/{away_code}")
def predict_glicko2(
    home_code: str,
    away_code: str,
    match_id: Optional[int] = Query(None, description="比赛 ID (v0.6.0+ 用于自动记录 prediction_log)"),
    db: Session = Depends(get_db),
) -> Dict:
    """Glicko-2 预测 - 比 Elo 准确率高 4-5 pp (62.7% vs 58.3%).

    训练数据: Hicruben 913 场国际赛 (2023-11 ~ 2026-06) walk-forward.
    """
    home = home_code.upper()
    away = away_code.upper()
    rh = g2_service.lookup_glicko2_rating(home)
    ra = g2_service.lookup_glicko2_rating(away)
    if rh is None or ra is None:
        missing = home if rh is None else away
        raise HTTPException(status_code=404, detail=f"球队 {missing} 不在 Glicko-2 数据中")
    pred = g2_service.predict_outcome(
        rh["rating"], rh["rd"],
        ra["rating"], ra["rd"],
        home_bonus=HOME_BONUS,
    )
    data = g2_service.load_glicko2_ratings()
    result = {
        "home": {"fifa_code": home, "rating": rh["rating"], "rd": rh["rd"], "volatility": rh["volatility"]},
        "away": {"fifa_code": away, "rating": ra["rating"], "rd": ra["rd"], "volatility": ra["volatility"]},
        "probabilities": {
            "home_win": pred["win_a"],
            "draw": pred["draw"],
            "away_win": pred["win_b"],
        },
        "expected_score": pred["expected_score"],
        "uncertainty": pred["uncertainty"],
        "model": "glicko2_v1",
        "data_source": "hicruben/world-cup-2026-prediction-model (913 matches walk-forward)",
        "data_as_of": data.get("generatedAt"),
        "metrics": data.get("metrics", {}),
    }
    # v0.6.0: 自动写 prediction_log
    if match_id is not None:
        try:
            from app.services.prediction_log import record_prediction
            record_prediction(
                db=db,
                match_id=match_id,
                model_version="v3_glicko2",
                pred_home_win=pred["win_a"],
                pred_draw=pred["draw"],
                pred_away_win=pred["win_b"],
                elo_home=int(rh["rating"]),
                elo_away=int(ra["rating"]),
                source="glicko2",
            )
        except Exception as e:
            print(f"[prediction_log] Glicko-2 写入失败: {e}")
    return result


@router.get("/elo/glicko2-ratings")
def glicko2_ratings(limit: Optional[int] = Query(None, ge=1, le=300)) -> List[Dict]:
    """Glicko-2 全队评分 (按 rating 降序)."""
    data = g2_service.load_glicko2_ratings()
    items = []
    for team, r in data.get("ratings", {}).items():
        items.append({
            "team_name": team,
            "rating": r["rating"],
            "rd": r["rd"],
            "volatility": r["volatility"],
        })
    items.sort(key=lambda x: -x["rating"])
    if limit:
        items = items[:limit]
    return items


@router.get("/elo/glicko2-metrics")
def glicko2_metrics() -> Dict:
    """Glicko-2 训练指标 (accuracy/RPS/Brier/LogLoss)."""
    data = g2_service.load_glicko2_ratings()
    return {
        "metrics": data.get("metrics", {}),
        "byYear": data.get("byYear", {}),
        "matchesApplied": data.get("matchesApplied", 0),
        "method": data.get("method", ""),
        "systemConstant": data.get("systemConstant", 0.5),
        "homeBonus": data.get("homeBonus", 70),
        "data_as_of": data.get("generatedAt"),
    }


# === v0.7.0a ModelBlend (Elo + Glicko-2 等权) ===

@router.get("/elo/predict-blend/{home_code}/{away_code}")
def predict_blend(
    home_code: str,
    away_code: str,
    w_elo: float = Query(0.5, ge=0.0, le=1.0, description="Elo 权重 (0-1, 默认 0.5)"),
    w_glicko2: float = Query(0.5, ge=0.0, le=1.0, description="Glicko-2 权重 (0-1, 默认 0.5)"),
    match_id: Optional[int] = Query(None, description="比赛 ID (v0.7.0a+ 自动记录 prediction_log)"),
    db: Session = Depends(get_db),
) -> Dict:
    """v0.7.0a ModelBlend: Elo (v1) + Glicko-2 (v3) 加权平均预测.

    等权 0.5/0.5 起步,可调(参数 w_elo / w_glicko2)。
    真正的三方融合(含市场赔率)在 v0.7.3。
    """
    if abs((w_elo + w_glicko2) - 1.0) > 1e-6:
        raise HTTPException(status_code=422, detail="w_elo + w_glicko2 必须等于 1.0")

    result = predict_match_blend(
        home_code=home_code,
        away_code=away_code,
        w_elo=w_elo,
        w_glicko2=w_glicko2,
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    # v0.7.0a: 自动写 prediction_log (model_version='v7a_blend')
    if match_id is not None:
        try:
            from app.services.prediction_log import record_prediction
            blended = result["blended"]["probabilities"]
            record_prediction(
                db=db,
                match_id=match_id,
                model_version="v7a_blend",
                pred_home_win=blended["home_win"],
                pred_draw=blended["draw"],
                pred_away_win=blended["away_win"],
                elo_home=result.get("home", {}).get("elo"),
                elo_away=result.get("away", {}).get("elo"),
                source="blend_elo_glicko2",
            )
        except Exception as e:
            print(f"[prediction_log] v7a_blend 写入失败: {e}")

    return result


# === 准确率 dashboard (v0.6.0+) ===

@router.get("/elo/accuracy-stats")
def accuracy_stats(
    model_version: Optional[str] = Query(None, description="模型版本 (v1_elo/v2_elo_enhanced/v3_glicko2), 默认全部"),
    days: Optional[int] = Query(None, ge=1, description="限定最近 N 天"),
    db: Session = Depends(get_db),
) -> Dict:
    """准确率统计 - 实时/历史 (从 prediction_log 表)."""
    from app.services.prediction_log import compute_accuracy_stats
    return compute_accuracy_stats(db, model_version=model_version, days=days)


# === v0.11 Forward-Testing 真 forward 准确率 ===

@router.get("/elo/live-accuracy")
def live_accuracy(
    is_live: Optional[bool] = Query(None, description="True=只看赛前实时预测 / False=backfill / None=全部"),
    model_version: Optional[str] = Query(None, description="模型版本过滤"),
    db: Session = Depends(get_db),
) -> Dict:
    """v0.11 Forward-Testing 端点: 真 forward 准确率 (赛前预测 + 已完赛).

    关键区别 vs /elo/accuracy-stats:
    - 该端点明确区分 backfill vs live (用 is_live 字段)
    - 默认无参数: 返回 live+backfill 全部 + 状态
    - is_live=true: 严格只算真 forward (lifespan startup + scheduler 6h 写)
    - 返回 data_status: 'no_data' / 'live_only' / 'backfill_only' / 'mixed'
    """
    from app.services.prediction_log import compute_live_accuracy
    return compute_live_accuracy(db, is_live=is_live, model_version=model_version)


@router.get("/elo/live-window-accuracy")
def live_window_accuracy(
    days: int = Query(7, ge=1, le=90, description="近 N 天"),
    db: Session = Depends(get_db),
) -> Dict:
    """v0.11 Forward-Testing mini-card: 近 N 天 live forward 准确率.

    用于 Cockpit widget. 永远只算 is_live=True, 排除 backfill 干扰.
    """
    from app.services.prediction_log import compute_live_window_accuracy
    return compute_live_window_accuracy(db, days=days)


@router.get("/elo/top-bias")
def top_bias(
    model_version: str = Query("v3_glicko2"),
    n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> List[Dict]:
    """Top N 偏差场次 (模型说某结果 80% 但实际相反 - 用于复盘)."""
    from app.services.prediction_log import get_top_prediction_bias
    return get_top_prediction_bias(db, model_version=model_version, n=n)


@router.get("/elo/weight-sweep")
def weight_sweep() -> Dict:
    """v0.7.4 weight sweep — 在 913 场历史 walk-forward 上找最佳 (w_elo, w_g2) 组合.

    评估 7 组权重:
    (1.0,0.0) (0.8,0.2) (0.6,0.4) (0.5,0.5) (0.4,0.6) (0.2,0.8) (0.0,1.0)

    4 指标: accuracy / brier / log_loss / roi_uniform
    winner 选 brier 最低.

    Returns:
        {results, baseline_50_50, winner, recommendation}
    """
    return run_weight_sweep()


@router.get("/elo/adaptive-weight/{home}/{away}")
def adaptive_weight(
    home: str,
    away: str,
    match_id: Optional[int] = Query(None, ge=1, description="可选,自动写 prediction_log"),
    db: Session = Depends(get_db),
) -> Dict:
    """v0.7.5 G2 自适应权重 — 按距上次比赛天数动态调整 w_g2.

    4 段: FRESH(≤7d) w_g2=1.0 / WARM(7-30d) 0.8 / STALE(30-90d) 0.6 / DORMANT(>90d) 0.5

    Args:
        home: 主队 FIFA code
        away: 客队 FIFA code
        match_id: 可选,匹配 ID,提供时自动写 prediction_log(model=adaptive)
    """
    from app.services.adaptive_weight import adaptive_weight_blend
    from app.services.elo import HOME_BONUS

    if home.upper() == away.upper():
        raise HTTPException(status_code=422, detail="主客队不能相同")

    # 校验球队存在
    home_team = db.query(Team).filter(Team.fifa_code == home.upper()).first()
    away_team = db.query(Team).filter(Team.fifa_code == away.upper()).first()
    if not home_team:
        raise HTTPException(status_code=404, detail=f"球队 {home.upper()} 不存在")
    if not away_team:
        raise HTTPException(status_code=404, detail=f"球队 {away.upper()} 不存在")

    r = adaptive_weight_blend(home, away, db)
    blend = r["blend_result"]

    # 自动写 prediction_log
    if match_id is not None and not blend.get("error") and blend.get("blended"):
        try:
            from app.services.prediction_log import record_prediction
            probs = blend["blended"]["probabilities"]
            record_prediction(
                db=db,
                match_id=match_id,
                model_version="v7b_adaptive",
                pred_home_win=probs["home_win"],
                pred_draw=probs["draw"],
                pred_away_win=probs["away_win"],
                elo_home=int(home_team.elo_rating) if home_team.elo_rating else None,
                elo_away=int(away_team.elo_rating) if away_team.elo_rating else None,
                source="adaptive",
            )
        except Exception as e:
            print(f"[prediction_log] adaptive 写入失败: {e}")

    return {
        "home": home_team.fifa_code,
        "away": away_team.fifa_code,
        "home_days_since_last": r["home_days_since_last"],
        "away_days_since_last": r["away_days_since_last"],
        "max_days": r["max_days_since_last"],
        "segment": r["segment"],
        "w_elo": r["w_elo"],
        "w_g2": r["w_g2"],
        "rationale": r["rationale"],
        "blend_result": blend,
        "model_version": r["model_version"],
    }


@router.get("/elo/calibrated-predict/{home}/{away}")
def calibrated_predict(
    home: str,
    away: str,
    db: Session = Depends(get_db),
) -> Dict:
    """v0.8.1 关停: 校准实验未达 1.5pp 门槛已下线.

    原 v0.7.8 Platt + v0.7.8.1 Isotonic 双方法 (git 保留,运行时不再调).
    详细关停原因见 deliverables/v0.8.1_calibration_sunset.md.
    """
    raise HTTPException(
        status_code=410,
        detail="v0.8.1 关停: G2 校准未达 1.5pp brier 改进门槛已下线,详见 deliverables/v0.8.1_calibration_sunset.md",
    )


@router.get("/elo/calibration-summary")
def calibration_summary() -> Dict:
    """v0.8.1 关停: Cockpit mini-card 已移除,端点保留为 410.

    详细关停原因见 deliverables/v0.8.1_calibration_sunset.md.
    """
    raise HTTPException(
        status_code=410,
        detail="v0.8.1 关停: 校准实验未达 1.5pp 门槛已下线,详见 deliverables/v0.8.1_calibration_sunset.md",
    )
