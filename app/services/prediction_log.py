"""PredictionLog 服务 - 自动追踪预测 + 赛后结算.

v0.6.0 核心组件:
  1. record_prediction() - 写一次预测到 log (dedup by match+model)
  2. settle_pending_predictions() - 调度器每 15min 扫已完赛比赛
  3. compute_accuracy_stats() - 出准确率 dashboard 数据

v0.7.0b 扩展:
  4. auto_log_predictions() - 遍历未来 7+1 天比赛,对每个 (match, model) 自动
     调 record_prediction。配合 lifespan startup 立即触发 + 6h 周期刷新
     形成"实盘预测自动累积"链路。
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import Match, PredictionLog, Team
from app.services.elo import predict_match, predict_match_enhanced, predict_match_blend, HOME_BONUS


def _score_to_outcome(home_score: int, away_score: int) -> str:
    """比分 → 'home' / 'draw' / 'away'."""
    if home_score > away_score:
        return "home"
    elif home_score < away_score:
        return "away"
    return "draw"


def _outcome_to_letter(outcome: str) -> str:
    """'home' → 'H' etc."""
    return {"home": "H", "draw": "D", "away": "A"}.get(outcome, "?")


def _compute_brier(p_h: float, p_d: float, p_a: float, outcome: str) -> float:
    """3-class Brier score (0=perfect, 2=worst)."""
    yh = 1.0 if outcome == "home" else 0.0
    yd = 1.0 if outcome == "draw" else 0.0
    ya = 1.0 if outcome == "away" else 0.0
    return (p_h - yh) ** 2 + (p_d - yd) ** 2 + (p_a - ya) ** 2


def _compute_log_loss(p_h: float, p_d: float, p_a: float, outcome: str) -> float:
    """LogLoss (-log(p_actual), 0=perfect, 大=差)."""
    p_map = {"home": p_h, "draw": p_d, "away": p_a}
    p = max(p_map[outcome], 1e-15)
    return -math.log(p)


def record_prediction(
    db: Session,
    match_id: int,
    model_version: str,
    pred_home_win: float,
    pred_draw: float,
    pred_away_win: float,
    elo_home: Optional[int] = None,
    elo_away: Optional[int] = None,
    source: str = "hicruben",
    is_live: bool = False,
    snapshot_group: Optional[str] = None,
) -> Optional[PredictionLog]:
    """记录一次预测到 log (dedup: 同 (match_id, model_version) 1 小时内不重复).

    v0.11 Forward-Testing 字段:
    - is_live: True=赛前实时预测 (lifespan/scheduler)/ False=backfill 历史回填
    - snapshot_group: 同一比赛同模型多次预测的快照组 (e.g. 赛前 7d/3d/1d)

    Returns:
        新建的 PredictionLog, 或 None (已存在未结算的旧记录)
    """
    # Dedup: 1 小时内同 (match, model) 已有未结算记录则跳过
    from datetime import timedelta
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    existing = (
        db.query(PredictionLog)
        .filter(
            PredictionLog.match_id == match_id,
            PredictionLog.model_version == model_version,
            PredictionLog.predicted_at >= one_hour_ago,
        )
        .first()
    )
    if existing:
        return None

    predicted_outcome = (
        "H" if pred_home_win >= pred_draw and pred_home_win >= pred_away_win
        else ("D" if pred_draw >= pred_away_win else "A")
    )

    log = PredictionLog(
        match_id=match_id,
        model_version=model_version,
        predicted_at=datetime.now(timezone.utc),
        pred_home_win=pred_home_win,
        pred_draw=pred_draw,
        pred_away_win=pred_away_win,
        predicted_outcome=predicted_outcome,
        elo_home=elo_home,
        elo_away=elo_away,
        source=source,
        is_live=is_live,
        snapshot_group=snapshot_group,
    )
    db.add(log)
    db.commit()
    return log


def settle_pending_predictions(db: Session) -> int:
    """扫描所有 已完赛比赛 + 比分非空, 结算 prediction_log.

    完赛判定: status='finished' OR status='live' + time_elapsed='finished'
    (wc26 sync 对 6/11 完赛的 MEX-RSA 仍标 'live' + time_elapsed='finished')

    Returns:
        结算的条数
    """
    # 1. 找出所有已完赛比赛 (兼容 wc26 的 'live'+'finished' 状态)
    finished_matches = (
        db.query(Match)
        .filter(Match.home_score.isnot(None))
        .filter(Match.away_score.isnot(None))
        .filter(
            (Match.status == "finished")
            | (
                (Match.status == "live")
                & (Match.time_elapsed == "finished")
            )
        )
        .all()
    )
    if not finished_matches:
        return 0

    settled_count = 0
    for m in finished_matches:
        actual_outcome = _score_to_outcome(m.home_score, m.away_score)
        # 2. 找该比赛所有未结算的 prediction_log
        pending = (
            db.query(PredictionLog)
            .filter(
                PredictionLog.match_id == m.id,
                PredictionLog.actual_outcome.is_(None),
            )
            .all()
        )
        for log in pending:
            log.actual_home_score = m.home_score
            log.actual_away_score = m.away_score
            log.actual_outcome = actual_outcome
            log.correct = 1 if log.predicted_outcome == _outcome_to_letter(actual_outcome) else 0
            log.brier_score = _compute_brier(log.pred_home_win, log.pred_draw, log.pred_away_win, actual_outcome)
            log.log_loss = _compute_log_loss(log.pred_home_win, log.pred_draw, log.pred_away_win, actual_outcome)
            log.settled_at = datetime.now(timezone.utc)
            settled_count += 1

    if settled_count > 0:
        db.commit()
    return settled_count


def compute_live_accuracy(
    db: Session,
    is_live: Optional[bool] = None,
    model_version: Optional[str] = None,
) -> Dict:
    """v0.11 Forward-Testing 核心: 计算真 forward 准确率.

    与 compute_accuracy_stats() 的关键区别:
    - 接受 is_live 参数: True 只看赛前实时预测 / False 只看 backfill / None 全部
    - 真实 forward 准确率 = is_live=True + 已完赛比赛 的 accuracy

    关键设计:
    1. 真 forward 含义: 预测在比赛前 (scheduler 写) 且结果已知 (完赛)
       - 自动满足: is_live=True + correct IS NOT NULL
    2. 区分 backfill vs live: 用 is_live 字段
    3. 返回每模型 + 整体 accuracy, brier, log_loss, sample size

    Args:
        db: Session
        is_live: True/False 过滤 / None 全部
        model_version: 指定模型 / None 全部

    Returns:
        {
            "is_live_filter": bool | None,
            "by_model": {
                model_version: {
                    "samples": int,
                    "accuracy": float | None,
                    "brier": float | None,
                    "log_loss": float | None,
                }
            },
            "overall": {
                "samples": int,
                "accuracy": float | None,
                "brier": float | None,
                "log_loss": float | None,
            },
            "data_status": "no_data" | "live_only" | "backfill_only" | "mixed",
            "note": str,  # 给前端的人类可读提示
        }
    """
    from sqlalchemy import func as sqlfunc

    # 1. base query: 已完赛 (correct IS NOT NULL)
    base = db.query(PredictionLog).filter(PredictionLog.correct.isnot(None))

    # 2. is_live 过滤
    if is_live is not None:
        base = base.filter(PredictionLog.is_live == is_live)

    # 3. model_version 过滤
    if model_version is not None:
        base = base.filter(PredictionLog.model_version == model_version)

    rows = base.all()

    if not rows:
        return {
            "is_live_filter": is_live,
            "by_model": {},
            "overall": {"samples": 0, "accuracy": None, "brier": None, "log_loss": None},
            "data_status": "no_data",
            "note": (
                "无真 forward 数据。"
                "原因是: scheduler 6h 跑 + lifespan startup 写预测 + wc26 sync 同步完赛结果."
                "6 月 17 日距世界杯开赛 17 天, 所有比赛未完赛."
                "开赛日 7 月 4 日后此端点会显示真 forward accuracy."
            ),
        }

    # 4. 数据状态判断
    n_live = sum(1 for r in rows if r.is_live)
    n_backfill = len(rows) - n_live
    if n_live == 0:
        data_status = "backfill_only"
    elif n_backfill == 0:
        data_status = "live_only"
    else:
        data_status = "mixed"

    # 5. 按模型分组
    by_model: Dict[str, List[PredictionLog]] = {}
    for r in rows:
        by_model.setdefault(r.model_version, []).append(r)

    def _aggregate(group: List[PredictionLog]) -> Dict:
        if not group:
            return {"samples": 0, "accuracy": None, "brier": None, "log_loss": None}
        n = len(group)
        n_correct = sum(r.correct for r in group if r.correct is not None)
        briers = [r.brier_score for r in group if r.brier_score is not None]
        log_losses = [r.log_loss for r in group if r.log_loss is not None]
        return {
            "samples": n,
            "accuracy": round(n_correct / n, 4) if n > 0 else None,
            "brier": round(sum(briers) / len(briers), 4) if briers else None,
            "log_loss": round(sum(log_losses) / len(log_losses), 4) if log_losses else None,
        }

    by_model_stats = {m: _aggregate(g) for m, g in by_model.items()}

    # 6. 整体
    overall = _aggregate(rows)

    # 7. 注释
    if is_live is True:
        note = (
            f"真 forward 准确率 (is_live=True, 赛前实时预测): "
            f"{overall['samples']} 场已完赛预测."
        )
    elif is_live is False:
        note = (
            f"Backfill 准确率 (is_live=False, 历史回填): "
            f"{overall['samples']} 场."
        )
    else:
        note = f"全部 (backfill + live): {overall['samples']} 场."

    return {
        "is_live_filter": is_live,
        "by_model": by_model_stats,
        "overall": overall,
        "data_status": data_status,
        "note": note,
    }


def compute_live_window_accuracy(
    db: Session,
    days: int = 7,
) -> Dict:
    """v0.11 Forward-Testing: 计算近 N 天 live forward 准确率.

    用于 Cockpit mini-card, 避免历史 backfill 干扰.

    Args:
        db: Session
        days: 近 N 天 (默认 7)

    Returns:
        {
            "days": int,
            "window_start": ISO8601,
            "window_end": ISO8601,
            "by_model": {model: {samples, accuracy, brier, log_loss}},
            "overall": {samples, accuracy, brier, log_loss},
            "note": str,
        }
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    base = (
        db.query(PredictionLog)
        .filter(PredictionLog.correct.isnot(None))
        .filter(PredictionLog.is_live == True)  # noqa: E712 - SQLAlchemy 字段
        .filter(PredictionLog.predicted_at >= window_start)
    )
    rows = base.all()

    if not rows:
        return {
            "days": days,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "by_model": {},
            "overall": {"samples": 0, "accuracy": None, "brier": None, "log_loss": None},
            "note": (
                f"近 {days} 天无 live forward 数据 (比赛未开赛或 scheduler 未跑)."
            ),
        }

    by_model: Dict[str, List[PredictionLog]] = {}
    for r in rows:
        by_model.setdefault(r.model_version, []).append(r)

    def _agg(group: List[PredictionLog]) -> Dict:
        n = len(group)
        n_correct = sum(r.correct for r in group if r.correct is not None)
        briers = [r.brier_score for r in group if r.brier_score is not None]
        log_losses = [r.log_loss for r in group if r.log_loss is not None]
        return {
            "samples": n,
            "accuracy": round(n_correct / n, 4) if n > 0 else None,
            "brier": round(sum(briers) / len(briers), 4) if briers else None,
            "log_loss": round(sum(log_losses) / len(log_losses), 4) if log_losses else None,
        }

    return {
        "days": days,
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "by_model": {m: _agg(g) for m, g in by_model.items()},
        "overall": _agg(rows),
        "note": f"近 {days} 天 live forward, {len(rows)} 场已完赛预测.",
    }


def compute_accuracy_stats(
    db: Session,
    model_version: Optional[str] = None,
    days: Optional[int] = None,
) -> Dict:
    """计算准确率 / RPS / Brier / LogLoss.

    Args:
        model_version: 筛选模型 (None = 全部)
        days: 限定最近 N 天 (None = 全部)

    Returns:
        {
            'n_total': int, 'n_settled': int, 'n_pending': int,
            'accuracy': float, 'rps': float, 'brier': float, 'log_loss': float,
            'by_outcome': {home: {...}, draw: {...}, away: {...}},
            'by_model': {model: {...}},
        }
    """
    q = db.query(PredictionLog)
    if model_version:
        q = q.filter(PredictionLog.model_version == model_version)
    if days:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = q.filter(PredictionLog.predicted_at >= cutoff)

    all_logs = q.all()
    n_total = len(all_logs)
    settled = [l for l in all_logs if l.actual_outcome is not None]
    pending = [l for l in all_logs if l.actual_outcome is None]
    n_settled = len(settled)
    n_pending = len(pending)

    if n_settled == 0:
        return {
            "n_total": n_total,
            "n_settled": 0,
            "n_pending": n_pending,
            "accuracy": None,
            "rps": None,
            "brier": None,
            "log_loss": None,
            "by_outcome": {},
            "by_model": {},
        }

    correct = sum(l.correct for l in settled)
    accuracy = correct / n_settled

    brier_avg = sum(l.brier_score or 0 for l in settled) / n_settled
    logloss_avg = sum(l.log_loss or 0 for l in settled) / n_settled

    # RPS
    rps_sum = 0.0
    for l in settled:
        if l.actual_outcome == "home":
            yh, yd, ya = 1, 0, 0
        elif l.actual_outcome == "draw":
            yh, yd, ya = 0, 1, 0
        else:
            yh, yd, ya = 0, 0, 1
        ph, pd, pa = l.pred_home_win, l.pred_draw, l.pred_away_win
        rps_sum += 0.5 * (
            (ph - yh) ** 2 +
            (ph + pd - yh - yd) ** 2
        )
    rps_avg = rps_sum / n_settled

    # 按 actual_outcome 分组
    by_outcome = {}
    for outcome in ("home", "draw", "away"):
        sub = [l for l in settled if l.actual_outcome == outcome]
        if sub:
            by_outcome[outcome] = {
                "n": len(sub),
                "accuracy": round(sum(l.correct for l in sub) / len(sub), 4),
            }

    # 按 model_version 分组
    by_model = {}
    models = set(l.model_version for l in settled)
    for mv in models:
        sub = [l for l in settled if l.model_version == mv]
        by_model[mv] = {
            "n": len(sub),
            "accuracy": round(sum(l.correct for l in sub) / len(sub), 4),
            "brier": round(sum(l.brier_score or 0 for l in sub) / len(sub), 4),
            "log_loss": round(sum(l.log_loss or 0 for l in sub) / len(sub), 4),
        }

    return {
        "n_total": n_total,
        "n_settled": n_settled,
        "n_pending": n_pending,
        "accuracy": round(accuracy, 4),
        "rps": round(rps_avg, 4),
        "brier": round(brier_avg, 4),
        "log_loss": round(logloss_avg, 4),
        "by_outcome": by_outcome,
        "by_model": by_model,
    }


def get_top_prediction_bias(db: Session, model_version: str = "v3_glicko2", n: int = 10) -> List[Dict]:
    """找出最大偏差场次 (模型说主胜 80% 但实际打平/客胜).

    Returns:
        List of {match_id, predicted, actual, confidence, surprise_score}
    """
    from sqlalchemy import desc
    pending_correct = (
        db.query(PredictionLog)
        .filter(
            PredictionLog.model_version == model_version,
            PredictionLog.actual_outcome.isnot(None),
            PredictionLog.correct == 0,
        )
        .all()
    )
    bias_list = []
    for l in pending_correct:
        # 找出预测的 confidence (最大概率)
        max_p = max(l.pred_home_win, l.pred_draw, l.pred_away_win)
        # 找出实际 outcome 的概率
        actual_p = {
            "home": l.pred_home_win,
            "draw": l.pred_draw,
            "away": l.pred_away_win,
        }[l.actual_outcome]
        # surprise = 模型 confidence - 给实际结果概率
        surprise = max_p - actual_p
        bias_list.append({
            "match_id": l.match_id,
            "predicted_outcome": l.predicted_outcome,
            "actual_outcome": l.actual_outcome,
            "confidence": round(max_p, 4),
            "actual_p": round(actual_p, 4),
            "surprise_score": round(surprise, 4),
            "brier": l.brier_score,
        })
    # 按 surprise 排序
    bias_list.sort(key=lambda x: -x["surprise_score"])
    return bias_list[:n]


# ============================================================
# v0.7.0b 自动写库 (lifespan startup + 6h 周期刷新)
# ============================================================


def _predict_v1(home_code: str, away_code: str) -> Optional[Dict]:
    """v1_elo: Elo M1 + Dixon-Coles. 返回 (ph, pd, pa, elo_home, elo_away) 或 None."""
    result = predict_match(home_code, away_code, source="hicruben")
    if result.get("error"):
        return None
    probs = result.get("probabilities", {})
    if probs.get("home_win") is None:
        return None
    return {
        "ph": probs["home_win"],
        "pd": probs["draw"],
        "pa": probs["away_win"],
        "elo_home": (result.get("home") or {}).get("elo"),
        "elo_away": (result.get("away") or {}).get("elo"),
    }


def _predict_v3(home_code: str, away_code: str) -> Optional[Dict]:
    """v3_glicko2: Glicko-2 + HOME_BONUS. 返回 (ph, pd, pa, rating_home, rating_away) 或 None."""
    from app.services import glicko2 as g2

    rh = g2.lookup_glicko2_rating(home_code.upper())
    ra = g2.lookup_glicko2_rating(away_code.upper())
    if not rh or not ra:
        return None
    pred = g2.predict_outcome(
        rating_a=rh["rating"],
        rd_a=rh["rd"],
        rating_b=ra["rating"],
        rd_b=ra["rd"],
        home_bonus=HOME_BONUS,
    )
    return {
        "ph": round(pred["win_a"], 4),
        "pd": round(pred["draw"], 4),
        "pa": round(pred["win_b"], 4),
        "elo_home": int(rh["rating"]),
        "elo_away": int(ra["rating"]),
    }


def _predict_v7a(home_code: str, away_code: str) -> Optional[Dict]:
    """v7a_blend: Elo + Glicko-2 等权平均. 返回 (ph, pd, pa, elo_home, elo_away) 或 None."""
    result = predict_match_blend(home_code, away_code, w_elo=0.5, w_glicko2=0.5)
    if result.get("error"):
        return None
    blended = result.get("blended", {})
    probs = blended.get("probabilities", {})
    if probs.get("home_win") is None:
        return None
    return {
        "ph": probs["home_win"],
        "pd": probs["draw"],
        "pa": probs["away_win"],
        "elo_home": (result.get("home") or {}).get("elo"),
        "elo_away": (result.get("away") or {}).get("elo"),
    }


# 模型注册表: model_version -> predict_fn(home_code, away_code) -> Dict | None
MODEL_REGISTRY: Dict[str, callable] = {
    "v1_elo": _predict_v1,
    "v3_glicko2": _predict_v3,
    "v7a_blend": _predict_v7a,
}


def auto_log_predictions(
    db: Session,
    models: Tuple[str, ...] = ("v1_elo", "v3_glicko2", "v7a_blend"),
    lookback_days: int = 1,
    lookahead_days: int = 7,
) -> Dict:
    """v0.7.0b 自动写库: 遍历未完赛比赛,对每个 (match, model) 调 record_prediction.

    范围: [now - lookback_days, now + lookahead_days] 内未完赛比赛
    写库去重: 沿用 record_prediction 1h dedup (同 match + model 1h 内不重写)
    单条错误隔离: 一条 predict 失败不影响其他 (match, model) 写入

    Args:
        db: SQLAlchemy Session
        models: 要写入的 model_version tuple,默认 3 模型 (v1_elo + v3_glicko2 + v7a_blend)
        lookback_days: 窗口起点(默认 1 天,允许写"刚完赛但还没结算"的可对账数据)
        lookahead_days: 窗口终点(默认 7 天,覆盖一周赛程)

    Returns:
        {
            "matches_scanned": int,
            "predictions_added": int,    # 新写入条数 (dedup 跳过的不算)
            "predictions_skipped": int,  # 1h dedup 跳过
            "by_model": {model: int},
            "errors": [{match_id, model, error_str}],
            "executed_at": ISO8601 str,
        }
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=lookback_days)
    window_end = now + timedelta(days=lookahead_days)

    # 1. 找窗口内未完赛比赛 (status != finished 或 比分有一方缺失)
    matches = (
        db.query(Match)
        .filter(Match.kickoff_at.isnot(None))
        .filter(Match.kickoff_at >= window_start)
        .filter(Match.kickoff_at <= window_end)
        .filter(
            (Match.home_score.is_(None)) | (Match.away_score.is_(None))
        )
        .all()
    )

    added = 0
    skipped = 0
    by_model = {m: 0 for m in models}
    errors: List[Dict] = []

    for m in matches:
        home_team = m.home_team
        away_team = m.away_team
        if not home_team or not away_team:
            continue
        home_code = home_team.fifa_code
        away_code = away_team.fifa_code
        if not home_code or not away_code:
            continue

        for model_name in models:
            predict_fn = MODEL_REGISTRY.get(model_name)
            if predict_fn is None:
                continue
            try:
                pred = predict_fn(home_code, away_code)
            except Exception as exc:
                errors.append({
                    "match_id": m.id,
                    "model": model_name,
                    "error": f"predict_fn: {str(exc)[:120]}",
                })
                continue
            if pred is None:
                # 缺数据,跳过但不记 error (正常情况: USA 等不在 Glicko-2 数据中)
                continue
            try:
                log = record_prediction(
                    db,
                    match_id=m.id,
                    model_version=model_name,
                    pred_home_win=pred["ph"],
                    pred_draw=pred["pd"],
                    pred_away_win=pred["pa"],
                    elo_home=pred.get("elo_home"),
                    elo_away=pred.get("elo_away"),
                    source="hicruben",
                    is_live=True,  # v0.11: lifespan/scheduler 自动写 = 实时预测
                )
                if log is not None:
                    added += 1
                    by_model[model_name] += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors.append({
                    "match_id": m.id,
                    "model": model_name,
                    "error": f"record_prediction: {str(exc)[:120]}",
                })

    return {
        "matches_scanned": len(matches),
        "predictions_added": added,
        "predictions_skipped": skipped,
        "by_model": by_model,
        "errors": errors,
        "executed_at": now.isoformat(),
    }
