"""v0.6.0: 将 backfill_prediction_log.py 输出导入 prediction_log 表.

用法:
  python scripts/load_backfill_to_db.py

数据来源: data/prediction_log_backfill.jsonl (1826 行: 913 Elo + 913 Glicko-2)
入库策略:
  - match_id 沿用 Hicruben 比赛 id (Match 表无外键约束, 不冲突)
  - source="backfill_hicruben_2018_2022_2026" (与实时区分)
  - 跳过已存在 (match_id, model_version) 重复
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import SessionLocal
from app.models import PredictionLog


def outcome_to_letter(s: str) -> str:
    return {"home": "H", "draw": "D", "away": "A"}.get(s, "H")


def outcome_to_full(letter: str) -> str:
    return {"H": "home", "D": "draw", "A": "away"}.get(letter, "home")


def compute_brier_logloss(ph, pd, pa, actual):
    """计算 Brier 和 LogLoss."""
    p = {"home": ph, "draw": pd, "away": pa}[actual]
    brier = (ph - (1 if actual == "home" else 0)) ** 2 \
        + (pd - (1 if actual == "draw" else 0)) ** 2 \
        + (pa - (1 if actual == "away" else 0)) ** 2
    # LogLoss: 仅算 actual 那一项, 避免 log(0)
    p_safe = max(p, 1e-7)
    log_loss = -math.log(p_safe)
    return brier, log_loss


def load_one(record: dict, db) -> bool:
    """入库一条记录, 返回 True=新插入, False=跳过(重复)."""
    match_id = record["match_id"]
    model = record["model"]
    # 转换: v1_elo_walkforward → v1_elo, v3_glicko2_walkforward → v3_glicko2
    if model == "v1_elo_walkforward":
        model_version = "v1_elo"
    elif model == "v3_glicko2_walkforward":
        model_version = "v3_glicko2"
    else:
        model_version = model

    # 查重
    exists = db.query(PredictionLog).filter(
        PredictionLog.match_id == match_id,
        PredictionLog.model_version == model_version,
        PredictionLog.source.like("backfill_%"),
    ).first()
    if exists:
        return False

    pred_outcome_full = outcome_to_full(record["predicted_outcome"])  # letter H/D/A → home/draw/away
    actual_outcome_full = record["actual_outcome"]  # 已经是 home/draw/away 全称
    correct = bool(record["correct"])

    brier, log_loss = compute_brier_logloss(
        record["ph"], record["pd"], record["pa"], actual_outcome_full,
    )

    # 解析日期
    try:
        date_obj = datetime.fromisoformat(record["date"])
        if date_obj.tzinfo is None:
            date_obj = date_obj.replace(tzinfo=timezone.utc)
    except Exception:
        date_obj = datetime.now(timezone.utc)

    row = PredictionLog(
        match_id=match_id,
        model_version=model_version,
        predicted_at=date_obj,
        pred_home_win=record["ph"],
        pred_draw=record["pd"],
        pred_away_win=record["pa"],
        predicted_outcome=pred_outcome_full,
        actual_home_score=None,  # Hicruben 数据没存原始比分
        actual_away_score=None,
        actual_outcome=actual_outcome_full,
        correct=correct,
        brier_score=round(brier, 6),
        log_loss=round(log_loss, 6),
        elo_home=None,  # walk-forward 没保留 Elo 状态
        elo_away=None,
        source="backfill_hicruben_2018_2022_2026",
        settled_at=date_obj,
    )
    db.add(row)
    return True


def main():
    jsonl_path = ROOT / "data" / "prediction_log_backfill.jsonl"
    if not jsonl_path.exists():
        print(f"❌ {jsonl_path} 不存在, 请先跑 backfill_prediction_log.py")
        sys.exit(1)

    records = [json.loads(line) for line in open(jsonl_path, encoding="utf-8")]
    print(f"读入 {len(records)} 条记录")

    db = SessionLocal()
    inserted = 0
    skipped = 0
    try:
        for r in records:
            if load_one(r, db):
                inserted += 1
            else:
                skipped += 1
            # 50 条 commit 一次
            if (inserted + skipped) % 50 == 0:
                db.commit()
                print(f"  进度: {inserted + skipped}/{len(records)} (inserted={inserted}, skipped={skipped})")
        db.commit()
    finally:
        db.close()

    print(f"\n✓ 入库完成: 新增 {inserted} 条, 跳过 {skipped} 条")


if __name__ == "__main__":
    main()
