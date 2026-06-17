"""v0.7.8 G2-only Platt scaling - 11 unit tests"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.calibration import (
    _logit, _sigmoid, platt_fit, platt_apply, fit_calibrators,
    calibrate_probs, walkforward_validate, load_g2_records, evaluate_all,
)


# ---------- _logit / _sigmoid ----------

def test_logit_0_returns_neg_inf_logit_clamped():
    """logit(0) 会 -inf, _logit 应被 eps clamp"""
    z = _logit(0.0)
    assert math.isfinite(z)


def test_sigmoid_logit_roundtrip():
    """sigmoid(logit(0.7)) ≈ 0.7"""
    for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
        assert abs(_sigmoid(_logit(p)) - p) < 1e-9


# ---------- platt_fit / apply 数学正确性 ----------

def test_platt_fit_identity_data_recovers_near_identity():
    """完美校准的合成数据: a≈0, b≈1"""
    p_actual = [0.1, 0.2, 0.5, 0.7, 0.9, 0.3, 0.4, 0.6, 0.8, 0.5]
    p_pred = p_actual.copy()
    a, b = platt_fit(p_actual, p_pred)
    # 完美校准: sigmoid(a + b*logit(p)) ≈ p, 应得 a≈0, b≈1
    assert abs(b - 1.0) < 0.2
    assert abs(a) < 0.5


def test_platt_apply_extreme_values_safe():
    """p=0 或 p=1 不应崩 (eps clamp)"""
    # platt_apply 用 _logit 内部已 clamp
    p_out = platt_apply(0.001, -0.1, 1.3)
    assert 0.0 <= p_out <= 1.0
    p_out2 = platt_apply(0.999, -0.1, 1.3)
    assert 0.0 <= p_out2 <= 1.0


def test_platt_fit_too_few_samples_returns_identity():
    """<5 样本应 fallback 到 identity (a=0, b=1)"""
    a, b = platt_fit([0.1, 0.2], [0.1, 0.2])
    assert a == 0.0 and b == 1.0


# ---------- fit_calibrators ----------

def test_fit_calibrators_returns_3_pairs():
    cals = fit_calibrators([
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home"},
        {"ph": 0.4, "pd": 0.4, "pa": 0.2, "actual_outcome": "draw"},
        {"ph": 0.3, "pd": 0.3, "pa": 0.4, "actual_outcome": "away"},
    ] * 20)
    assert hasattr(cals, "a_h") and hasattr(cals, "b_h")
    assert hasattr(cals, "a_d") and hasattr(cals, "b_d")
    assert hasattr(cals, "a_a") and hasattr(cals, "b_a")
    assert all(isinstance(getattr(cals, k), float) for k in ["a_h", "b_h", "a_d", "b_d", "a_a", "b_a"])


def test_fit_calibrators_ignores_unknown_outcomes():
    """actual_outcome 不是 home/draw/away 应跳过, 不崩"""
    cals = fit_calibrators([
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "cancelled"},
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home"},
    ] * 10)
    # 至少能 fit 出 (a, b) 不报异常
    assert cals.a_h != 0 or cals.b_h != 1  # 至少有数值


# ---------- calibrate_probs ----------

def test_calibrate_probs_normalized_sum_1():
    """calibrate_probs 输出三元组应和为 1"""
    cals = fit_calibrators([
        {"ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home"},
    ] * 50)
    ch, cd, ca = calibrate_probs(0.5, 0.3, 0.2, cals)
    assert abs((ch + cd + ca) - 1.0) < 1e-6
    assert 0 <= ch <= 1 and 0 <= cd <= 1 and 0 <= ca <= 1


def test_calibrate_probs_monotonic_preserved():
    """raw ph > pd > pa, cal 后应保持同样顺序"""
    cals = fit_calibrators([
        {"ph": 0.7, "pd": 0.2, "pa": 0.1, "actual_outcome": "home"},
    ] * 50)
    ch, cd, ca = calibrate_probs(0.7, 0.2, 0.1, cals)
    assert ch > cd > ca


# ---------- walkforward_validate ----------

def test_walkforward_validate_empty_split_returns_error():
    """0 样本应返回 error"""
    result = walkforward_validate([], test_ratio=0.2)
    assert "error" in result


def test_walkforward_validate_913_g2_real_data():
    """913 场真数据: raw vs calibrated, 验证 brier 改进 ≥ 0 (calibration 不会变差)"""
    records = load_g2_records()
    assert len(records) == 913
    result = walkforward_validate(records, test_ratio=0.2)
    assert "raw" in result and "calibrated" in result
    assert "calibrators" in result
    # brier 改进 ≥ 0 (calibration 不变差)
    assert result["calibrated"]["brier"] <= result["raw"]["brier"] + 0.001


# ---------- evaluate_all / load_g2_records ----------

def test_load_g2_records_returns_only_g2():
    """应只取 v3_glicko2_walkforward, 不取 v1_elo_walkforward"""
    records = load_g2_records()
    assert len(records) == 913
    for r in records:
        assert r["model"] == "v3_glicko2_walkforward"


def test_evaluate_all_brier_improvement_positive():
    """913 场全量: calibrated brier 应 <= raw brier"""
    records = load_g2_records()
    result = evaluate_all(records)
    assert result["raw_brier"] > 0
    assert result["calibrated_brier"] <= result["raw_brier"]
    # 113 场 baseline 0.5120, 期望 0.495-0.515 区间
    assert 0.45 < result["calibrated_brier"] < 0.55
