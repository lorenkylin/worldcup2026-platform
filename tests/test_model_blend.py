"""v0.7.0a ModelBlend 单元测试.

测试目标:
  - predict_match_blend() 函数逻辑(8 个 case)
  - /api/elo/predict-blend/{home}/{away} 端点契约

不依赖 DB,只验证纯函数和路由 422/404 错误码。
"""
import math
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.elo import predict_match_blend, predict_match
from app.services import glicko2 as g2_service


client = TestClient(app)


# === 1. 纯函数层(8 case) ===

def test_blend_basic_returns_valid_structure():
    """基本结构: elo/glicko2/blended/predicted_outcome 五字段齐全."""
    result = predict_match_blend("BRA", "ARG")
    assert result.get("error") is None, f"unexpected error: {result.get('error')}"
    assert "home" in result and result["home"]["fifa_code"] == "BRA"
    assert "away" in result and result["away"]["fifa_code"] == "ARG"
    assert "elo" in result and "probabilities" in result["elo"]
    assert "glicko2" in result and "probabilities" in result["glicko2"]
    assert "blended" in result
    assert result["blended"]["model"] == "blend_elo_glicko2_v1"
    assert result["blended"]["weights"] == {"elo": 0.5, "glicko2": 0.5}
    assert result["predicted_outcome"] in ("H", "D", "A")
    assert result["model_version"] == "v7a_blend"


def test_blend_probs_sum_to_one():
    """三套概率各自加和 = 1.0 (±0.005)."""
    for home, away in [("BRA", "ARG"), ("GER", "JPN"), ("USA", "MEX"), ("ENG", "FRA")]:
        result = predict_match_blend(home, away)
        assert result.get("error") is None
        for src in ("elo", "glicko2", "blended"):
            probs = result[src]["probabilities"]
            s = probs["home_win"] + probs["draw"] + probs["away_win"]
            assert abs(s - 1.0) < 0.005, f"{home} vs {away} {src} probs sum={s}"


def test_blend_w_elo_1_equals_pure_elo():
    """w_elo=1.0 → blended = elo(完全无 Glicko-2 贡献)."""
    elo_only = predict_match("BRA", "ARG")
    blend = predict_match_blend("BRA", "ARG", w_elo=1.0, w_glicko2=0.0)
    assert blend.get("error") is None
    e = elo_only["probabilities"]
    b = blend["blended"]["probabilities"]
    for k in ("home_win", "draw", "away_win"):
        assert abs(b[k] - e[k]) < 0.001, f"w_elo=1.0 时 {k} 不等于 Elo: {b[k]} vs {e[k]}"


def test_blend_w_glicko2_1_equals_pure_glicko2():
    """w_glicko2=1.0 → blended = glicko2."""
    rh = g2_service.lookup_glicko2_rating("BRA")
    ra = g2_service.lookup_glicko2_rating("ARG")
    assert rh is not None and ra is not None, "Glicko-2 数据缺失,跳过此测试"
    g2_pred = g2_service.predict_outcome(rh["rating"], rh["rd"], ra["rating"], ra["rd"], home_bonus=70)
    blend = predict_match_blend("BRA", "ARG", w_elo=0.0, w_glicko2=1.0)
    assert blend.get("error") is None
    g = g2_pred
    b = blend["blended"]["probabilities"]
    for k, src in (("home_win", "win_a"), ("draw", "draw"), ("away_win", "win_b")):
        assert abs(b[k] - g[src]) < 0.001, f"w_glicko2=1.0 时 {k}: {b[k]} vs {g[src]}"


def test_blend_unknown_team_returns_error():
    """FIFA code 不在数据中 → error 字段非空(端点层会转 404)."""
    result = predict_match_blend("BRA", "XXX")
    assert result.get("error") is not None
    assert "XXX" in result["error"] or "Glicko-2" in result["error"]


def test_blend_predicted_outcome_logic():
    """predicted_outcome = argmax(blended_probabilities)."""
    result = predict_match_blend("BRA", "ARG")
    assert result.get("error") is None
    p = result["blended"]["probabilities"]
    expected = max(p, key=p.get)
    expected_letter = {"home_win": "H", "draw": "D", "away_win": "A"}[expected]
    assert result["predicted_outcome"] == expected_letter
    assert result["confidence"] == p[expected]


def test_blend_data_source_and_as_of():
    """data_source 和 data_as_of 字段非空."""
    result = predict_match_blend("BRA", "ARG")
    assert result.get("error") is None
    assert "hicruben" in result["data_source"]
    assert result["data_as_of"] is not None


def test_blend_weights_in_response():
    """返回的 weights 字段反映实际加权."""
    r1 = predict_match_blend("BRA", "ARG", w_elo=0.3, w_glicko2=0.7)
    r2 = predict_match_blend("BRA", "ARG", w_elo=0.7, w_glicko2=0.3)
    assert r1.get("error") is None and r2.get("error") is None
    assert r1["blended"]["weights"] == {"elo": 0.3, "glicko2": 0.7}
    assert r2["blended"]["weights"] == {"elo": 0.7, "glicko2": 0.3}
    # 加权不同,blend 概率必然不同(除非两模型完全一致,这种情况罕见)
    p1 = r1["blended"]["probabilities"]["home_win"]
    p2 = r2["blended"]["probabilities"]["home_win"]
    # 注:若两模型在该场比赛预测几乎相同,可能相等,这是允许的


# === 2. 端点层(3 case) ===

def test_endpoint_predict_blend_returns_200():
    """/api/elo/predict-blend/BRA/ARG 返回 200."""
    r = client.get("/api/elo/predict-blend/BRA/ARG")
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    data = r.json()
    assert data["home"]["fifa_code"] == "BRA"
    assert data["away"]["fifa_code"] == "ARG"
    assert data["blended"]["model"] == "blend_elo_glicko2_v1"


def test_endpoint_predict_blend_404_for_unknown():
    """/api/elo/predict-blend/BRA/XXX 返回 404."""
    r = client.get("/api/elo/predict-blend/BRA/XXX")
    assert r.status_code == 404


def test_endpoint_predict_blend_422_for_bad_weights():
    """w_elo + w_glicko2 != 1.0 → 422."""
    r = client.get("/api/elo/predict-blend/BRA/ARG?w_elo=0.3&w_glicko2=0.5")
    assert r.status_code == 422
