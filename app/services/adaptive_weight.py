"""v0.7.5 G2 Adaptive Weight - 按距上次比赛天数动态调整 w_g2.

策略: 取 max(home_days_since_last, away_days_since_last) 作为"两队数据陈旧度",
按 4 段(FRESH / WARM / STALE / DORMANT) 选权重:
  FRESH   (≤7天)   : w_g2=1.0 (新鲜数据,信 G2)
  WARM    (7-30天)  : w_g2=0.8 (G2 加 Elo 平衡)
  STALE   (30-90天) : w_g2=0.6 (G2 数据陈旧,加 Elo)
  DORMANT (>90天)   : w_g2=0.5 (数据不可信,回 v0.7.0a baseline)

设计动机: v0.7.4 walk-forward 显示 w_g2=1.0 在 913 场准确率最高 (+1.42pp vs 50/50),
但 G2 的 Glicko-2 评分依赖"最近比赛"更新,数据 stale 时 RD 反而偏低(已被压缩),
预测区间会过窄。Adaptive 段位让 w_g2 随数据新鲜度平滑过渡。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import Match


# === 4 段权重常量 (集中管理) ===
SEGMENT_WEIGHTS = {
    "fresh":    {"w_elo": 0.0, "w_g2": 1.0, "max_days": 7},
    "warm":     {"w_elo": 0.2, "w_g2": 0.8, "max_days": 30},
    "stale":    {"w_elo": 0.4, "w_g2": 0.6, "max_days": 90},
    "dormant":  {"w_elo": 0.5, "w_g2": 0.5, "max_days": None},  # 上限
}

SEGMENT_RATIONALE = {
    "fresh":   "两队 {days} 天内都有比赛,数据新鲜,信任 G2 单独",
    "warm":    "两队 {days} 天内有比赛,G2 稍 stale,加 Elo 平衡",
    "stale":   "两队已 {days} 天未赛,G2 数据陈旧,加 Elo 提升稳健",
    "dormant": "两队已 {days} 天未赛,数据高度不可信,回 v0.7.0a 50/50 baseline",
}


def decide_segment(max_days: int) -> str:
    """根据 max(home_days, away_days) 返回 segment 名称.

    Args:
        max_days: 两队中较长的未赛天数
    Returns:
        "fresh" | "warm" | "stale" | "dormant"
    """
    if max_days <= 7:
        return "fresh"
    if max_days <= 30:
        return "warm"
    if max_days <= 90:
        return "stale"
    return "dormant"


def days_since_last_match(db: Session, team_code: str, before_date: Optional[datetime] = None) -> int:
    """查 team_code 在 before_date 之前的最后一场比赛距 before_date 多少天.

    Returns:
        天数(int). 没有历史时返回 9999 (视为 DORMANT).
    """
    from app.models import Team

    team = db.query(Team).filter(Team.fifa_code == team_code).first()
    if team is None:
        return 9999

    q = db.query(Match).filter(
        (Match.home_team_id == team.id) | (Match.away_team_id == team.id),
        Match.kickoff_at.isnot(None),
    )
    if before_date is not None:
        if before_date.tzinfo is not None:
            before_date = before_date.replace(tzinfo=None)
        q = q.filter(Match.kickoff_at < before_date)
    last = q.order_by(Match.kickoff_at.desc()).first()
    if last is None or last.kickoff_at is None:
        return 9999

    if before_date is None:
        before_date = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = before_date - last.kickoff_at
    return max(0, delta.days)


def adaptive_weight_blend(home_code: str, away_code: str, db: Session) -> Dict:
    """v0.7.5 核心: 查两队最后比赛天数 → 选段 → 调 predict_match_blend.

    Args:
        home_code: 主队 FIFA code
        away_code: 客队 FIFA code
        db: SQLAlchemy Session (查 Match 表)

    Returns:
        dict 含 segment / w_elo / w_g2 / rationale / days_since_last / blend_result
    """
    from app.services.elo import predict_match_blend

    home_code_u = home_code.upper()
    away_code_u = away_code.upper()

    home_days = days_since_last_match(db, home_code_u)
    away_days = days_since_last_match(db, away_code_u)
    max_days = max(home_days, away_days)
    segment = decide_segment(max_days)
    weights = SEGMENT_WEIGHTS[segment]
    rationale = SEGMENT_RATIONALE[segment].format(days=max_days)

    blend = predict_match_blend(
        home_code=home_code_u,
        away_code=away_code_u,
        w_elo=weights["w_elo"],
        w_glicko2=weights["w_g2"],
    )

    return {
        "home_code": home_code_u,
        "away_code": away_code_u,
        "home_days_since_last": home_days,
        "away_days_since_last": away_days,
        "max_days_since_last": max_days,
        "segment": segment,
        "w_elo": weights["w_elo"],
        "w_g2": weights["w_g2"],
        "rationale": rationale,
        "blend_result": blend,
        "model_version": "v7b_adaptive",
    }


def walkforward_adaptive_validate(db: Session) -> Dict:
    """913 场 walk-forward: 模拟对每场比赛算自适应段位,统计 accuracy/brier/log_loss.

    用于回归测试: 验证 v0.7.5 adaptive 在历史数据上比 v0.7.0a 50/50 不退化。
    """
    from app.services.elo import predict_match_blend

    matches = (
        db.query(Match)
        .filter(Match.status == "finished", Match.home_score.isnot(None), Match.away_score.isnot(None))
        .order_by(Match.kickoff_at.asc())
        .all()
    )
    n = len(matches)
    if n == 0:
        return {"n_matches": 0, "accuracy": 0, "brier": 0, "log_loss": 0}

    n_correct = 0
    brier_sum = 0.0
    log_loss_sum = 0.0
    import math

    for m in matches:
        from app.models import Team
        home = db.query(Team).get(m.home_team_id)
        away = db.query(Team).get(m.away_team_id)
        if not home or not away:
            continue
        before = m.kickoff_at
        home_days = days_since_last_match(db, home.fifa_code, before_date=before)
        away_days = days_since_last_match(db, away.fifa_code, before_date=before)
        max_days = max(home_days, away_days)
        seg = decide_segment(max_days)
        w = SEGMENT_WEIGHTS[seg]

        try:
            r = predict_match_blend(home.fifa_code, away.fifa_code, w_elo=w["w_elo"], w_glicko2=w["w_g2"])
        except Exception:
            continue
        if r.get("error") or not r.get("blended"):
            continue
        probs = r["blended"]["probabilities"]
        actual = "H" if m.home_score > m.away_score else ("A" if m.away_score > m.home_score else "D")
        pred = r["predicted_outcome"]
        if pred == actual:
            n_correct += 1
        # 3-class brier
        actual_vec = {"H": [1, 0, 0], "D": [0, 1, 0], "A": [0, 0, 1]}[actual]
        pred_vec = [probs["home_win"], probs["draw"], probs["away_win"]]
        brier_sum += sum((p - a) ** 2 for p, a in zip(pred_vec, actual_vec))
        # log loss
        p_actual = pred_vec[actual_vec.index(1)]
        log_loss_sum += -math.log(max(p_actual, 1e-9))

    return {
        "n_matches": n,
        "n_correct": n_correct,
        "accuracy": round(n_correct / n, 4),
        "brier": round(brier_sum / n, 4),
        "log_loss": round(log_loss_sum / n, 4),
    }
