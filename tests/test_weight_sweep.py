"""v0.7.4 weight sweep 单元测试."""
import math
import os
import tempfile
import json
from unittest.mock import patch

import pytest

from app.services.weight_sweep import (
    DEFAULT_WEIGHTS,
    ELO_MODEL,
    G2_MODEL,
    SweepResult,
    load_match_pairs,
    run_weight_sweep,
    _blend,
    _evaluate,
)


# === 单元测试: 纯函数 ===


def test_blend_arithmetic():
    """_blend: w=0.5 时等权平均."""
    assert _blend(0.4, 0.6, 0.5) == pytest.approx(0.5)
    assert _blend(0.4, 0.6, 1.0) == pytest.approx(0.4)
    assert _blend(0.4, 0.6, 0.0) == pytest.approx(0.6)


def test_blend_5_5():
    """50/50: ph+pd+pa 必 = 1.0 (Elo/G2 已分别归一)."""
    elo = (0.5, 0.3, 0.2)
    g2 = (0.4, 0.4, 0.2)
    blended = tuple(_blend(e, g, 0.5) for e, g in zip(elo, g2))
    assert sum(blended) == pytest.approx(1.0, abs=1e-9)


# === 集成测试: 临时文件 ===


def _write_temp_jsonl(rows):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def _make_pair(match_id, ph_e, pd_e, pa_e, ph_g, pd_g, pa_g, actual):
    return [
        {
            "match_id": match_id,
            "date": "2024-01-01",
            "home_team": "AAA",
            "away_team": "BBB",
            "ph": ph_e, "pd": pd_e, "pa": pa_e,
            "actual_outcome": actual,
            "predicted_outcome": "H" if actual == "home" else "D",
            "correct": 1,
            "model": ELO_MODEL,
        },
        {
            "match_id": match_id,
            "date": "2024-01-01",
            "home_team": "AAA",
            "away_team": "BBB",
            "ph": ph_g, "pd": pd_g, "pa": pa_g,
            "actual_outcome": actual,
            "predicted_outcome": "H" if actual == "home" else "D",
            "correct": 1,
            "model": G2_MODEL,
        },
    ]


def test_load_match_pairs_pairing():
    """2 场共有,1 场 Elo 独有 → 只返回 2 场."""
    rows = (
        _make_pair(1, 0.5, 0.3, 0.2, 0.6, 0.2, 0.2, "home")
        + _make_pair(2, 0.3, 0.4, 0.3, 0.4, 0.3, 0.3, "draw")
        + [{
            "match_id": 3, "date": "2024-01-01", "home_team": "X", "away_team": "Y",
            "ph": 0.5, "pd": 0.3, "pa": 0.2, "actual_outcome": "home",
            "predicted_outcome": "H", "correct": 1, "model": ELO_MODEL,
        }]
    )
    path = _write_temp_jsonl(rows)
    try:
        with patch("app.services.weight_sweep._default_path", return_value=path):
            pairs = load_match_pairs()
    finally:
        os.unlink(path)
    assert len(pairs) == 2
    assert {p["match_id"] for p in pairs} == {1, 2}
    assert pairs[0]["ph_elo"] == pytest.approx(0.5)
    assert pairs[0]["ph_g2"] == pytest.approx(0.6)


def test_evaluate_perfect_g2():
    """G2 100% 命中 (但 ph_e=0.2 < pa_e=0.6 实际 home),纯 G2 优于纯 Elo."""
    pairs = [{
        "match_id": 1,
        "date": "2024-01-01",
        "home": "A", "away": "B",
        "actual": "home",
        "ph_elo": 0.2, "pd_elo": 0.2, "pa_elo": 0.6,
        "ph_g2":  0.6, "pd_g2":  0.2, "pa_g2":  0.2,
    }]
    r_elo = _evaluate(pairs, w_elo=1.0)
    r_g2 = _evaluate(pairs, w_elo=0.0)
    assert r_elo.accuracy == 0.0
    assert r_g2.accuracy == 1.0
    assert r_g2.brier < r_elo.brier


def test_run_weight_sweep_returns_7_results():
    """run_weight_sweep 跑 7 组权重."""
    rows = _make_pair(1, 0.5, 0.3, 0.2, 0.4, 0.3, 0.3, "home")
    path = _write_temp_jsonl(rows)
    try:
        with patch("app.services.weight_sweep._default_path", return_value=path):
            out = run_weight_sweep()
    finally:
        os.unlink(path)
    assert out["n_matches"] == 1
    assert out["weights_evaluated"] == 7
    assert len(out["results"]) == 7
    weights = [(r["w_elo"], r["w_g2"]) for r in out["results"]]
    assert (0.5, 0.5) in weights
    assert (1.0, 0.0) in weights
    assert (0.0, 1.0) in weights
    assert out["winner"]["metric_used"] == "brier"


def test_run_weight_sweep_winner_picks_lowest_brier():
    """winner 是 brier 最低."""
    rows = (
        _make_pair(1, 0.5, 0.3, 0.2, 0.6, 0.2, 0.2, "home")
        + _make_pair(2, 0.3, 0.4, 0.3, 0.4, 0.3, 0.3, "draw")
    )
    path = _write_temp_jsonl(rows)
    try:
        with patch("app.services.weight_sweep._default_path", return_value=path):
            out = run_weight_sweep()
    finally:
        os.unlink(path)
    briers = [r["brier"] for r in out["results"]]
    winner = out["winner"]
    winner_brier = next(r["brier"] for r in out["results"] if r["w_elo"] == winner["w_elo"])
    assert winner_brier == min(briers)


def test_run_weight_sweep_baseline_is_50_50():
    """baseline_50_50 必须 w_elo=0.5."""
    rows = _make_pair(1, 0.5, 0.3, 0.2, 0.4, 0.3, 0.3, "home")
    path = _write_temp_jsonl(rows)
    try:
        with patch("app.services.weight_sweep._default_path", return_value=path):
            out = run_weight_sweep()
    finally:
        os.unlink(path)
    assert out["baseline_50_50"]["w_elo"] == 0.5
    assert "accuracy" in out["baseline_50_50"]


@pytest.mark.slow
def test_run_weight_sweep_with_real_data():
    """默认路径真实数据 - 跑出 913 场 winner."""
    out = run_weight_sweep()
    assert out["n_matches"] == 913
    assert out["weights_evaluated"] == 7
    # 已知结论: Glicko-2 单独最优
    assert out["winner"]["w_elo"] == 0.0
    assert out["winner"]["w_g2"] == 1.0
    assert out["winner"]["accuracy"] >= 0.62
    assert out["baseline_50_50"]["accuracy"] >= 0.60
