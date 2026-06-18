"""v0.13.0 MarketBlend 单元测试.

覆盖:
  - /api/elo/predict-market-blend/{home}/{away} 正常返回含 market 的三方融合
  - 缺市场赔率时 fallback 到 Elo + Glicko-2
  - 权重和不等于 1 时 422
  - 未知球队 404
  - match_id 触发 prediction_log 写入
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import MatchOdds

client = TestClient(app)


@pytest.fixture
def _seed_odds_for_match_1(db_session):
    """给模板 DB 的 match_id=1 (MEX vs RSA) 写入默认盘口赔率."""
    db_session.add(
        MatchOdds(
            match_id=1,
            bookmaker="betpawa",
            home_win=2.10,
            draw=3.40,
            away_win=3.60,
            source="test",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()


def test_market_blend_endpoint_returns_three_way_blend(_seed_odds_for_match_1):
    """正常情况返回 Elo + Glicko-2 + market 三方融合."""
    r = client.get("/api/elo/predict-market-blend/MEX/RSA?match_id=1")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["home"]["fifa_code"] == "MEX"
    assert data["away"]["fifa_code"] == "RSA"
    assert data["match_id"] == 1
    assert data["model_version"] == "v7c_market_blend"
    assert data["fallback_reason"] is None
    assert "market" in data
    assert data["market"]["bookmaker"] == "betpawa"
    assert "blended" in data
    assert data["blended"]["model"] == "market_blend_v1"
    assert data["blended"]["weights"] == {"elo": 0.4, "glicko2": 0.3, "market": 0.3}
    probs = data["blended"]["probabilities"]
    assert abs(probs["home_win"] + probs["draw"] + probs["away_win"] - 1.0) < 1e-3
    assert data["predicted_outcome"] in ("H", "D", "A")


def test_market_blend_fallback_when_no_odds():
    """无市场赔率时 fallback 到 Elo + Glicko-2, 不报错."""
    r = client.get("/api/elo/predict-market-blend/BRA/ARG")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["model_version"] == "v7c_market_blend_fallback"
    assert data["fallback_reason"] == "market_odds_unavailable"
    assert data["market"] is None
    assert data["blended"]["weights"]["market"] == 0.0
    probs = data["blended"]["probabilities"]
    assert abs(probs["home_win"] + probs["draw"] + probs["away_win"] - 1.0) < 1e-3


def test_market_blend_rejects_invalid_weights():
    """三方权重和不等于 1 时返回 422."""
    r = client.get("/api/elo/predict-market-blend/MEX/RSA?w_elo=0.5&w_glicko2=0.3&w_market=0.3")
    assert r.status_code == 422
    assert "必须等于 1.0" in r.json()["detail"]


def test_market_blend_unknown_team_returns_404():
    """未知球队返回 404."""
    r = client.get("/api/elo/predict-market-blend/XXX/YYY")
    assert r.status_code == 404


def test_market_blend_writes_prediction_log(_seed_odds_for_match_1, db_session):
    """带 match_id 时自动写入 prediction_log."""
    from app.models import PredictionLog

    # 清理旧记录
    db_session.query(PredictionLog).filter(
        PredictionLog.match_id == 1,
        PredictionLog.model_version == "v7c_market_blend",
    ).delete()
    db_session.commit()

    r = client.get("/api/elo/predict-market-blend/MEX/RSA?match_id=1")
    assert r.status_code == 200, r.text

    rows = (
        db_session.query(PredictionLog)
        .filter(
            PredictionLog.match_id == 1,
            PredictionLog.model_version == "v7c_market_blend",
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].source == "market_blend"
    assert rows[0].predicted_outcome in ("H", "D", "A")
