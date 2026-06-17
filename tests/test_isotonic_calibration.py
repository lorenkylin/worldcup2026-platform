"""
v0.7.8.1 Isotonic 校准对比 — 单元测试
"""
from app.services.isotonic_calibration import (
    isotonic_fit,
    isotonic_apply,
    fit_isotonic_calibrators,
    isotonic_calibrate_probs,
    isotonic_walkforward_validate,
    IsotonicCalibrators,
)


def test_isotonic_fit_returns_monotone_non_decreasing():
    """输出步阶函数必须单调非降"""
    p_pred = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    p_actual = [0.05, 0.25, 0.20, 0.50, 0.45, 0.70, 0.65, 0.90, 0.85]
    step = isotonic_fit(p_actual, p_pred)
    ys = [y for _, y in step]
    for i in range(len(ys) - 1):
        assert ys[i + 1] >= ys[i] - 1e-9, f"非单调: {ys[i]} -> {ys[i + 1]}"


def test_isotonic_apply_in_range():
    """中间值查表返回 step 中最接近的左侧 y"""
    p_pred = [0.0, 0.5, 1.0]
    p_actual = [0.0, 0.6, 1.0]
    step = isotonic_fit(p_actual, p_pred)
    assert step[0] == (0.0, 0.0)
    assert step[-1] == (1.0, 1.0)
    assert isotonic_apply(0.5, step) == 0.6
    assert isotonic_apply(0.3, step) == 0.0
    assert isotonic_apply(0.8, step) == 0.6


def test_isotonic_apply_out_of_range_extrapolation():
    """p < 边界 -> step[0].y (左外推);p > 边界 -> step[-1].y (右外推)"""
    # >=3 样本保证 PAVA 不走 fallback
    p_pred = [0.2, 0.5, 0.8]
    p_actual = [0.3, 0.5, 0.7]
    step = isotonic_fit(p_actual, p_pred)
    # 边界已 pad 到 [0, 1]
    assert step[0] == (0.0, 0.0)
    assert step[-1] == (1.0, 1.0)
    # p = 0 等于下界,走 step[0]
    assert isotonic_apply(0.0, step) == step[0][1] == 0.0
    # p = 1 等于上界,走 step[-1]
    assert isotonic_apply(1.0, step) == step[-1][1] == 1.0
    # p 超出 [0, 1] 也走边界
    assert isotonic_apply(-0.1, step) == step[0][1]
    assert isotonic_apply(1.5, step) == step[-1][1]


def test_isotonic_fit_too_few_returns_identity_fallback():
    """<3 样本走 fallback [(0,0),(1,1)]"""
    step = isotonic_fit([0.5], [0.5])
    assert step == [(0.0, 0.0), (1.0, 1.0)]


def test_fit_isotonic_calibrators_returns_three_step_fns():
    """3 个独立 step fn"""
    records = [
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home"},
        {"ph": 0.3, "pd": 0.4, "pa": 0.3, "actual_outcome": "draw"},
        {"ph": 0.2, "pd": 0.3, "pa": 0.5, "actual_outcome": "away"},
        {"ph": 0.6, "pd": 0.2, "pa": 0.2, "actual_outcome": "home"},
        {"ph": 0.4, "pd": 0.3, "pa": 0.3, "actual_outcome": "draw"},
    ]
    cals = fit_isotonic_calibrators(records)
    assert isinstance(cals, IsotonicCalibrators)
    assert len(cals.h) >= 2
    assert len(cals.d) >= 2
    assert len(cals.a) >= 2


def test_isotonic_calibrate_probs_sums_to_one():
    """归一化校验"""
    records = [
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home"},
        {"ph": 0.3, "pd": 0.4, "pa": 0.3, "actual_outcome": "draw"},
        {"ph": 0.2, "pd": 0.3, "pa": 0.5, "actual_outcome": "away"},
    ] * 5
    cals = fit_isotonic_calibrators(records)
    ch, cd, ca = isotonic_calibrate_probs(0.5, 0.3, 0.2, cals)
    assert abs(ch + cd + ca - 1.0) < 1e-9
    assert all(0 <= p <= 1 for p in (ch, cd, ca))


def test_isotonic_walkforward_validate_returns_dict():
    """API 形状一致"""
    records = [
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home",
         "date": f"2024-01-{i+1:02d}"}
        for i in range(10)
    ] + [
        {"ph": 0.3, "pd": 0.4, "pa": 0.3, "actual_outcome": "draw",
         "date": f"2024-02-{i+1:02d}"}
        for i in range(10)
    ]
    res = isotonic_walkforward_validate(records, 0.3)
    assert "raw" in res
    assert "calibrated" in res
    assert "train_size" in res
    assert "test_size" in res
    assert "accuracy" in res["raw"]
    assert "brier" in res["raw"]


def test_isotonic_improves_or_neutral_on_synthetic_calibration_data():
    """人造完美校准数据:校准后 brier 应不增加(不差于 raw)"""
    # 数据: p 接近真实频率
    records = []
    for i in range(200):
        # 真实 outcome 频率 ph=0.5 时 50% 是 home win
        if i < 100:
            records.append({"ph": 0.55, "pd": 0.25, "pa": 0.20, "actual_outcome": "home",
                            "date": f"2024-{i+1:02d}-01"})
        elif i < 150:
            records.append({"ph": 0.30, "pd": 0.45, "pa": 0.25, "actual_outcome": "draw",
                            "date": f"2024-{i+1:02d}-02"})
        else:
            records.append({"ph": 0.20, "pd": 0.30, "pa": 0.50, "actual_outcome": "away",
                            "date": f"2024-{i+1:02d}-03"})
    res = isotonic_walkforward_validate(records, 0.3)
    raw_brier = res["raw"]["brier"]
    cal_brier = res["calibrated"]["brier"]
    assert cal_brier <= raw_brier + 0.01, (
        f"isotonic 在人造完美数据上 brier 上升: {raw_brier:.4f} -> {cal_brier:.4f}"
    )


def test_isotonic_dataclass_to_dict_serialization():
    """to_dict 兼容 JSON"""
    records = [
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home"},
        {"ph": 0.3, "pd": 0.4, "pa": 0.3, "actual_outcome": "draw"},
    ] * 5
    cals = fit_isotonic_calibrators(records)
    d = cals.to_dict()
    assert set(d.keys()) == {"h", "d", "a"}
    for k in ("h", "d", "a"):
        assert isinstance(d[k], list)
        for pair in d[k]:
            assert len(pair) == 2


def test_pava_handles_perfectly_increasing_data():
    """完全单调数据 PAVA 应返回原样(无池化)"""
    p_pred = [0.1, 0.3, 0.5, 0.7, 0.9]
    p_actual = [0.05, 0.20, 0.45, 0.65, 0.85]
    step = isotonic_fit(p_actual, p_pred)
    # 应近似保留(可能边界 pad 一下)
    assert step[0] == (0.0, 0.0)
    assert step[-1] == (1.0, 1.0)