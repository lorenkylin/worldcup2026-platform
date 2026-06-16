"""PredictionLog 服务 - 自动追踪预测 + 赛后结算.

v0.6.0 核心组件:
  1. record_prediction() - 写一次预测到 log (dedup by match+model)
  2. settle_pending_predictions() - 调度器每 15min 扫已完赛比赛
  3. compute_accuracy_stats() - 出准确率 dashboard 数据
"""
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import Match, PredictionLog, Team
from app.services.elo import predict_match, predict_match_enhanced, HOME_BONUS


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
) -> Optional[PredictionLog]:
    """记录一次预测到 log (dedup: 同 (match_id, model_version) 1 小时内不重复).

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
