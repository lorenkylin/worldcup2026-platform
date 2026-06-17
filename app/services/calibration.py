"""
v0.7.8 G2-only Platt scaling

Public API:
  - platt_fit(p_actual, p_pred) -> (a, b)        # 1-D logistic regression
  - platt_apply(p, a, b)         -> float          # sigmoid(a + b * logit(p))
  - fit_calibrators(records)     -> Calibrators   # 3 pairs (a_h, b_h), ...
  - calibrate_probs(ph, pd, pa, cals) -> tuple    # 归一化 (sum=1)
  - walkforward_validate(records, test_ratio) -> dict

数据源: data/prediction_log_backfill.jsonl (913 场, model=v3_glicko2_walkforward)
"""
from __future__ import annotations

import math
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def platt_fit(p_actual: List[float], p_pred: List[float]) -> Tuple[float, float]:
    """
    Fit Platt scaling: 实际概率 ≈ sigmoid(a + b * logit(p_pred))
    用 scipy-free L-BFGS 替代:简单 gradient descent on brier loss.

    L = sum (sigmoid(a + b*z_i) - y_i)^2
    dL/da = 2 * sum (s_i - y_i) * s_i * (1-s_i)
    dL/db = 2 * sum (s_i - y_i) * s_i * (1-s_i) * z_i

    2000 步 + a=0 b=1 init;经验证在 913 场稳定收敛
    """
    if len(p_actual) != len(p_pred) or len(p_actual) < 5:
        return 0.0, 1.0  # fallback to identity

    a, b = 0.0, 1.0
    lr = 0.05
    n = len(p_actual)
    z = [_logit(p) for p in p_pred]

    for step in range(2000):
        grad_a = 0.0
        grad_b = 0.0
        for zi, yi in zip(z, p_actual):
            s = _sigmoid(a + b * zi)
            diff = s - yi
            si = s * (1 - s)
            grad_a += 2 * diff * si
            grad_b += 2 * diff * si * zi
        grad_a /= n
        grad_b /= n
        a -= lr * grad_a
        b -= lr * grad_b
        # 防 b 太小导致 logit 退化为常量
        if abs(b) < 0.1:
            b = 0.1 if b >= 0 else -0.1

    return float(a), float(b)


def platt_apply(p: float, a: float, b: float) -> float:
    return _sigmoid(a + b * _logit(p))


@dataclass
class Calibrators:
    a_h: float
    b_h: float
    a_d: float
    b_d: float
    a_a: float
    b_a: float

    def to_dict(self) -> dict:
        return {
            "a_h": self.a_h, "b_h": self.b_h,
            "a_d": self.a_d, "b_d": self.b_d,
            "a_a": self.a_a, "b_a": self.b_a,
        }


def fit_calibrators(records: List[dict]) -> Calibrators:
    """
    records: 来自 prediction_log_backfill.jsonl 的行, 含 ph/pd/pa + actual_outcome
    """
    ph_pred, ph_actual = [], []
    pd_pred, pd_actual = [], []
    pa_pred, pa_actual = [], []

    for r in records:
        ao = r.get("actual_outcome")
        if ao == "home":
            ph_pred.append(r["ph"]); ph_actual.append(1.0)
            pd_pred.append(r["pd"]); pd_actual.append(0.0)
            pa_pred.append(r["pa"]); pa_actual.append(0.0)
        elif ao == "draw":
            ph_pred.append(r["ph"]); ph_actual.append(0.0)
            pd_pred.append(r["pd"]); pd_actual.append(1.0)
            pa_pred.append(r["pa"]); pa_actual.append(0.0)
        elif ao == "away":
            ph_pred.append(r["ph"]); ph_actual.append(0.0)
            pd_pred.append(r["pd"]); pd_actual.append(0.0)
            pa_pred.append(r["pa"]); pa_actual.append(1.0)

    a_h, b_h = platt_fit(ph_actual, ph_pred)
    a_d, b_d = platt_fit(pd_actual, pd_pred)
    a_a, b_a = platt_fit(pa_actual, pa_pred)
    return Calibrators(a_h, b_h, a_d, b_d, a_a, b_a)


def calibrate_probs(
    ph: float, pd: float, pa: float, cals: Calibrators
) -> Tuple[float, float, float]:
    """对三元组独立校准,然后归一化 (sum=1)"""
    ph2 = platt_apply(ph, cals.a_h, cals.b_h)
    pd2 = platt_apply(pd, cals.a_d, cals.b_d)
    pa2 = platt_apply(pa, cals.a_a, cals.b_a)
    s = ph2 + pd2 + pa2
    if s <= 0:
        return 1/3, 1/3, 1/3
    return ph2 / s, pd2 / s, pa2 / s


def _brier(records: List[dict]) -> float:
    """
    3-way Brier score (sum form, /n).
    与 v0.7.4 weight_sweep._evaluate_brier 一致:
        sum_i (p_h - y_h)^2 + (p_d - y_d)^2 + (p_a - y_a)^2, 平均每场。
    913 场 G2 校准前 baseline ≈ 0.5120。
    """
    s = 0.0
    n = len(records)
    for r in records:
        for p, a in [(r["ph"], 1 if r["actual_outcome"] == "home" else 0),
                     (r["pd"], 1 if r["actual_outcome"] == "draw" else 0),
                     (r["pa"], 1 if r["actual_outcome"] == "away" else 0)]:
            s += (p - a) ** 2
    return s / n


def _accuracy(records: List[dict]) -> float:
    n = len(records)
    if n == 0:
        return 0.0
    correct = 0
    for r in records:
        pmax = max(r["ph"], r["pd"], r["pa"])
        if r["ph"] == pmax:
            pred = "home"
        elif r["pd"] == pmax:
            pred = "draw"
        else:
            pred = "away"
        if pred == r["actual_outcome"]:
            correct += 1
    return correct / n


def walkforward_validate(
    records: List[dict], test_ratio: float = 0.2
) -> dict:
    """
    Time-ordered split: 前 test_ratio 比例作为 test set,后 (1-test_ratio) 训练。
    返回: train_size, test_size, raw (test 段原 accuracy/brier),
          calibrated (test 段校准后 accuracy/brier)
    """
    records = sorted(records, key=lambda r: r.get("date", ""))
    n = len(records)
    split = int(n * (1 - test_ratio))
    train = records[:split]
    test = records[split:]

    if not train or not test:
        return {"error": "empty split", "n": n, "split": split}

    cals = fit_calibrators(train)

    test_cal = []
    for r in test:
        ch, cd, ca = calibrate_probs(r["ph"], r["pd"], r["pa"], cals)
        test_cal.append({
            "ph": ch, "pd": cd, "pa": ca,
            "actual_outcome": r["actual_outcome"],
        })

    return {
        "train_size": len(train),
        "test_size": len(test),
        "raw": {
            "accuracy": _accuracy(test),
            "brier": _brier(test),
        },
        "calibrated": {
            "accuracy": _accuracy(test_cal),
            "brier": _brier(test_cal),
        },
        "calibrators": cals.to_dict(),
    }


def load_g2_records(path: str | Path = "data/prediction_log_backfill.jsonl") -> List[dict]:
    """只取 v3_glicko2_walkforward 行"""
    out = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("model") == "v3_glicko2_walkforward":
                out.append(r)
    return out


def evaluate_all(records: List[dict]) -> dict:
    """Full-sample 评估 raw vs 后验校准(无 split,只看 overall 校准能力)"""
    cals = fit_calibrators(records)
    cal = []
    for r in records:
        ch, cd, ca = calibrate_probs(r["ph"], r["pd"], r["pa"], cals)
        cal.append({
            "ph": ch, "pd": cd, "pa": ca,
            "actual_outcome": r["actual_outcome"],
        })
    return {
        "n": len(records),
        "raw_accuracy": _accuracy(records),
        "raw_brier": _brier(records),
        "calibrated_accuracy": _accuracy(cal),
        "calibrated_brier": _brier(cal),
        "calibrators": cals.to_dict(),
    }


# v0.7.10 calibration summary cache (Cockpit mini-card)
import threading
from datetime import datetime, timezone

_calibration_summary_cache: dict = {"data": None, "computed_at": None}
_calibration_summary_lock = threading.Lock()
_CALIBRATION_SUMMARY_TTL_SECONDS = 21600  # 6h


def get_calibration_summary() -> dict:
    """v0.7.10 轻量摘要: 3 个 brier 改进百分点 + 训练样本数.
    进程内 cache, 6h TTL. Cockpit 频繁刷新只算 1 次.

    Returns:
        {
            "training_samples": int,
            "platt_full_fit_pp": float,        # 负数=校准后 brier 变低
            "platt_walkforward_80_20_pp": float,
            "isotonic_walkforward_80_20_pp": float,
            "cache_ttl_seconds": 21600,
            "computed_at": ISO 8601 str (UTC)
        }
    """
    from app.services.isotonic_calibration import isotonic_walkforward_validate
    now = datetime.now(timezone.utc)
    cached = _calibration_summary_cache
    if cached["data"] is not None and cached["computed_at"] is not None:
        age = (now - cached["computed_at"]).total_seconds()
        if age < _CALIBRATION_SUMMARY_TTL_SECONDS:
            return cached["data"]
    with _calibration_summary_lock:
        # double-check after acquire lock
        if cached["data"] is not None and cached["computed_at"] is not None:
            age = (now - cached["computed_at"]).total_seconds()
            if age < _CALIBRATION_SUMMARY_TTL_SECONDS:
                return cached["data"]
        records = load_g2_records()
        platt_wf = walkforward_validate(records, test_ratio=0.2)
        platt_full = evaluate_all(records)
        iso_wf = isotonic_walkforward_validate(records, test_ratio=0.2)
        platt_wf_pp = round(
            (platt_wf["raw"]["brier"] - platt_wf["calibrated"]["brier"]) * 100, 3
        )
        platt_full_pp = round(
            (platt_full["raw_brier"] - platt_full["calibrated_brier"]) * 100, 3
        )
        iso_wf_pp = round(
            (iso_wf["raw"]["brier"] - iso_wf["calibrated"]["brier"]) * 100, 3
        )
        data = {
            "training_samples": len(records),
            "platt_full_fit_pp": platt_full_pp,
            "platt_walkforward_80_20_pp": platt_wf_pp,
            "isotonic_walkforward_80_20_pp": iso_wf_pp,
            "cache_ttl_seconds": _CALIBRATION_SUMMARY_TTL_SECONDS,
            "computed_at": now.isoformat().replace("+00:00", "Z"),
        }
        cached["data"] = data
        cached["computed_at"] = now
        return data
