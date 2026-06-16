"""v0.7.4 weight sweep — 在历史 913 场 walk-forward 数据上找最佳 (w_elo, w_g2) 组合.

数据源: data/prediction_log_backfill.jsonl
  - 913 行 v1_elo_walkforward (ph/pd/pa 来自 Elo, 排序按时间)
  - 913 行 v3_glicko2_walkforward (ph/pd/pa 来自 Glicko-2, 与 Elo 同一 match_id)

混合公式 (per match):
  p_h_blend = w_elo * p_h_elo + w_g2 * p_h_g2
  p_d_blend = w_elo * p_d_elo + w_g2 * p_d_g2
  p_a_blend = w_elo * p_a_elo + w_g2 * p_a_g2
  # 重新归一以防 (w_elo + w_g2) ≠ 1.0
  sum_p = p_h + p_d + p_a
  p_h /= sum_p; p_d /= sum_p; p_a /= sum_p
  predicted = argmax(p_h, p_d, p_a) -> H/D/A

4 评估指标:
  - accuracy:    命中率 (correct = predicted == actual)
  - brier:       3-class Brier, mean((p_h - y_h)² + (p_d - y_d)² + (p_a - y_a)²)
  - log_loss:    mean(-log(p_actual))
  - roi_uniform: 假设按模型概率等额下注(单注 1 单位,命中得 1/0),胜场收益

winner 选择策略: brier 最低 (综合最强).
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ELO_MODEL = "v1_elo_walkforward"
G2_MODEL = "v3_glicko2_walkforward"

DEFAULT_WEIGHTS: List[Tuple[float, float]] = [
    (1.0, 0.0),
    (0.8, 0.2),
    (0.6, 0.4),
    (0.5, 0.5),
    (0.4, 0.6),
    (0.2, 0.8),
    (0.0, 1.0),
]


@dataclass
class SweepResult:
    """单组 (w_elo, w_g2) 的回测结果."""
    w_elo: float
    w_g2: float
    n_matches: int
    accuracy: float
    brier: float
    log_loss: float
    roi_uniform: float


def _default_path() -> str:
    """定位 prediction_log_backfill.jsonl,允许多种运行模式."""
    candidates = [
        os.environ.get("BACKFILL_JSONL", ""),
        "data/prediction_log_backfill.jsonl",
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "prediction_log_backfill.jsonl"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    raise FileNotFoundError(
        "prediction_log_backfill.jsonl not found. "
        "Set BACKFILL_JSONL env var or place file under data/."
    )


def load_match_pairs(path: Optional[str] = None) -> List[Dict]:
    """按 match_id 配对 Elo + G2 预测,返回 [{match_id, date, home, away, actual, ph_elo, pd_elo, pa_elo, ph_g2, pd_g2, pa_g2}, ...]."""
    fp = path or _default_path()
    elo_by_match: Dict[int, Dict] = {}
    g2_by_match: Dict[int, Dict] = {}

    with open(fp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            model = row.get("model")
            mid = row.get("match_id")
            if model == ELO_MODEL:
                elo_by_match[mid] = row
            elif model == G2_MODEL:
                g2_by_match[mid] = row

    common = sorted(set(elo_by_match) & set(g2_by_match))
    out: List[Dict] = []
    for mid in common:
        e = elo_by_match[mid]
        g = g2_by_match[mid]
        out.append({
            "match_id": mid,
            "date": e.get("date"),
            "home": e.get("home_team"),
            "away": e.get("away_team"),
            "actual": e.get("actual_outcome"),
            "ph_elo": float(e.get("ph", 0.0)),
            "pd_elo": float(e.get("pd", 0.0)),
            "pa_elo": float(e.get("pa", 0.0)),
            "ph_g2": float(g.get("ph", 0.0)),
            "pd_g2": float(g.get("pd", 0.0)),
            "pa_g2": float(g.get("pa", 0.0)),
        })
    return out


def _blend(p_elo: float, p_g2: float, w_elo: float) -> float:
    return w_elo * p_elo + (1.0 - w_elo) * p_g2


def _evaluate(pairs: List[Dict], w_elo: float) -> SweepResult:
    n = 0
    correct = 0
    brier_sum = 0.0
    log_loss_sum = 0.0
    roi_sum = 0.0

    for p in pairs:
        ph = _blend(p["ph_elo"], p["ph_g2"], w_elo)
        pd_ = _blend(p["pd_elo"], p["pd_g2"], w_elo)
        pa = _blend(p["pa_elo"], p["pa_g2"], w_elo)
        s = ph + pd_ + pa
        if s <= 0:
            continue
        ph /= s
        pd_ /= s
        pa /= s

        # 预测
        if ph >= pd_ and ph >= pa:
            pred = "home"
        elif pd_ >= pa:
            pred = "draw"
        else:
            pred = "away"

        actual = p["actual"]
        if actual not in ("home", "draw", "away"):
            continue
        n += 1
        if pred == actual:
            correct += 1
            roi_sum += 1.0
        roi_sum -= 1.0  # 每次下注 3 注 (H/D/A) 1 单位,期望 ROI 仅看正确率差

        y_h = 1.0 if actual == "home" else 0.0
        y_d = 1.0 if actual == "draw" else 0.0
        y_a = 1.0 if actual == "away" else 0.0
        brier_sum += (ph - y_h) ** 2 + (pd_ - y_d) ** 2 + (pa - y_a) ** 2

        p_actual = ph if actual == "home" else (pd_ if actual == "draw" else pa)
        # log_loss clip 防 log(0)
        p_actual = max(p_actual, 1e-9)
        log_loss_sum += -math.log(p_actual)

    return SweepResult(
        w_elo=w_elo,
        w_g2=1.0 - w_elo,
        n_matches=n,
        accuracy=correct / n if n else 0.0,
        brier=brier_sum / n if n else 0.0,
        log_loss=log_loss_sum / n if n else 0.0,
        # roi_normalized per match (3 注,赢 1 输 0)
        roi_uniform=roi_sum / n if n else 0.0,
    )


def run_weight_sweep(
    pairs: Optional[List[Dict]] = None,
    weights: Optional[List[Tuple[float, float]]] = None,
) -> Dict:
    """跑所有 (w_elo, w_g2) 组合,返回 {results: [...], winner: {...}, baseline: {...}}."""
    if pairs is None:
        pairs = load_match_pairs()
    if weights is None:
        weights = DEFAULT_WEIGHTS

    results: List[SweepResult] = []
    for w_elo, w_g2 in weights:
        results.append(_evaluate(pairs, w_elo))

    # 选 brier 最低
    winner = min(results, key=lambda r: (r.brier, -r.accuracy))
    baseline = next(r for r in results if abs(r.w_elo - 0.5) < 1e-9)

    return {
        "n_matches": len(pairs),
        "elo_model": ELO_MODEL,
        "g2_model": G2_MODEL,
        "weights_evaluated": len(results),
        "results": [
            {
                "w_elo": r.w_elo,
                "w_g2": r.w_g2,
                "n_matches": r.n_matches,
                "accuracy": round(r.accuracy, 4),
                "brier": round(r.brier, 4),
                "log_loss": round(r.log_loss, 4),
                "roi_uniform": round(r.roi_uniform, 4),
            }
            for r in results
        ],
        "baseline_50_50": {
            "w_elo": baseline.w_elo,
            "accuracy": round(baseline.accuracy, 4),
            "brier": round(baseline.brier, 4),
            "log_loss": round(baseline.log_loss, 4),
            "roi_uniform": round(baseline.roi_uniform, 4),
        },
        "winner": {
            "w_elo": winner.w_elo,
            "w_g2": winner.w_g2,
            "accuracy": round(winner.accuracy, 4),
            "brier": round(winner.brier, 4),
            "log_loss": round(winner.log_loss, 4),
            "roi_uniform": round(winner.roi_uniform, 4),
            "metric_used": "brier",
        },
        "recommendation": (
            f"推荐使用 w_elo={winner.w_elo:.1f}, w_g2={1 - winner.w_elo:.1f}, "
            f"brier={winner.brier:.4f}, accuracy={winner.accuracy:.4f}. "
            f"相比 v0.7.0a 默认 (0.5, 0.5), brier 变化 {winner.brier - baseline.brier:+.4f}."
        ),
    }
