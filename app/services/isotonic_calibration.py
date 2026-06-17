"""
v0.7.8.1 Isotonic 校准对比 (scipy-free pool adjacent violators)

Public API:
  - isotonic_fit(p_actual, p_pred) -> List[Tuple[float, float]]  # PAVA 步阶函数
  - isotonic_apply(p, step_fn)     -> float                         # 查表 + 边界外推
  - fit_isotonic_calibrators(records) -> IsotonicCalibrators
  - isotonic_calibrate_probs(ph, pd, pa, cals) -> tuple
  - isotonic_walkforward_validate(records, test_ratio) -> dict

与 v0.7.8 platt 比较,看是否能突破 1.5pp brier 门槛
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class IsotonicCalibrators:
    h: List[Tuple[float, float]]  # [(p_pred, p_actual_smoothed)] for home
    d: List[Tuple[float, float]]
    a: List[Tuple[float, float]]

    def to_dict(self):
        return {"h": self.h, "d": self.d, "a": self.a}


def isotonic_fit(
    p_actual: List[float], p_pred: List[float]
) -> List[Tuple[float, float]]:
    """
    Pool Adjacent Violators Algorithm (PAVA)
    保证输出单调非降 (对概率校准而言:y 应随 x 单调非降)
    返回 sorted (p_pred, p_smoothed) 列表

    算法:
      1. 按 p_pred 升序排 (x, y) 对
      2. 维护 blocks (每 block 是 (avg_x, avg_y, count))
      3. 后 block avg_y < 前 block avg_y → 合并 (pool adjacent violators)
      4. 合并后重算 avg_x, avg_y, count
    """
    if len(p_actual) != len(p_pred) or len(p_actual) < 3:
        return [(0.0, 0.0), (1.0, 1.0)]

    # 1. sort
    pairs = sorted(zip(p_pred, p_actual), key=lambda x: x[0])

    # 2-3. PAVA
    # block = [x_sum, y_sum, count]
    blocks = [[pairs[0][0], pairs[0][1], 1]]
    for i in range(1, len(pairs)):
        x, y = pairs[i]
        blocks.append([x, y, 1])
        # 检查最后两个 block 是否违反单调
        while len(blocks) >= 2:
            prev = blocks[-2]
            cur = blocks[-1]
            prev_avg_y = prev[1] / prev[2]
            cur_avg_y = cur[1] / cur[2]
            if cur_avg_y < prev_avg_y:
                # pool
                prev[0] += cur[0]
                prev[1] += cur[1]
                prev[2] += cur[2]
                blocks.pop()
            else:
                break

    # 4. 输出 step function:每 block 取 (avg_x, avg_y)
    step_fn = [(b[0] / b[2], b[1] / b[2]) for b in blocks]

    # 边界保护:首尾强制 [0, 0] [1, 1] 让外推有锚点
    if step_fn[0][0] > 0.0:
        step_fn.insert(0, (0.0, 0.0))
    if step_fn[-1][0] < 1.0:
        step_fn.append((1.0, 1.0))

    return step_fn


def isotonic_apply(
    p: float, step_fn: List[Tuple[float, float]]
) -> float:
    """
    查表 + 边界外推:
      - p < step_fn[0].x → step_fn[0].y (左外推)
      - p > step_fn[-1].x → step_fn[-1].y (右外推)
      - 中间 → 找最近 x_i ≤ p,返回对应 y_i (左连续,标准 PAVA 输出约定)
    """
    if not step_fn:
        return p
    if p <= step_fn[0][0]:
        return step_fn[0][1]
    if p >= step_fn[-1][0]:
        return step_fn[-1][1]
    for i in range(len(step_fn) - 1):
        x0, y0 = step_fn[i]
        x1, _ = step_fn[i + 1]
        if x0 <= p < x1:
            return y0
    return step_fn[-1][1]


def fit_isotonic_calibrators(records: List[dict]) -> IsotonicCalibrators:
    """对 h/d/a 三组独立 PAVA 拟合"""
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

    return IsotonicCalibrators(
        h=isotonic_fit(ph_actual, ph_pred),
        d=isotonic_fit(pd_actual, pd_pred),
        a=isotonic_fit(pa_actual, pa_pred),
    )


def isotonic_calibrate_probs(
    ph: float, pd: float, pa: float, cals: IsotonicCalibrators
) -> Tuple[float, float, float]:
    """独立查表后归一化"""
    ph2 = isotonic_apply(ph, cals.h)
    pd2 = isotonic_apply(pd, cals.d)
    pa2 = isotonic_apply(pa, cals.a)
    s = ph2 + pd2 + pa2
    if s <= 0:
        return 1 / 3, 1 / 3, 1 / 3
    return ph2 / s, pd2 / s, pa2 / s


def _brier(records: List[dict]) -> float:
    """与 calibration.py._brier 一致"""
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


def isotonic_walkforward_validate(
    records: List[dict], test_ratio: float = 0.2
) -> dict:
    """与 v0.7.8 walkforward_validate 同 API,可直接对比"""
    records = sorted(records, key=lambda r: r.get("date", ""))
    n = len(records)
    split = int(n * (1 - test_ratio))
    train = records[:split]
    test = records[split:]

    if not train or not test:
        return {"error": "empty split", "n": n, "split": split}

    cals = fit_isotonic_calibrators(train)

    test_cal = []
    for r in test:
        ch, cd, ca = isotonic_calibrate_probs(r["ph"], r["pd"], r["pa"], cals)
        test_cal.append({
            "ph": ch, "pd": cd, "pa": ca,
            "actual_outcome": r["actual_outcome"],
        })

    return {
        "train_size": len(train),
        "test_size": len(test),
        "raw": {"accuracy": _accuracy(test), "brier": _brier(test)},
        "calibrated": {"accuracy": _accuracy(test_cal), "brier": _brier(test_cal)},
        "calibrators": cals.to_dict(),
    }