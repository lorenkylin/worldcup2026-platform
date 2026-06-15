"""StatsBomb Elo 数据源测试.

覆盖：
- 队名映射
- StatsBomb Elo JSON 生成与加载
- 服务层 _get_team_elo_with_source fallback
- API source 参数
- compare 端点
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import statsbomb_elo as sb
from app.services.elo import (
    _get_team_elo_with_source,
    predict_match,
    get_top_elo,
    compare_predictions,
)
from app.services.statsbomb_elo import SB_NAME_TO_FIFA


# === 单元测试 ===

def test_team_name_mapping_covers_known_teams():
    """已知 StatsBomb 队名应正确映射到 FIFA code."""
    assert SB_NAME_TO_FIFA["Argentina"] == "ARG"
    assert SB_NAME_TO_FIFA["Brazil"] == "BRA"
    assert SB_NAME_TO_FIFA["United States"] == "USA"
    assert SB_NAME_TO_FIFA["South Korea"] == "KOR"
    assert SB_NAME_TO_FIFA["Cape Verde Islands"] == "CPV"
    assert SB_NAME_TO_FIFA["Congo DR"] == "COD"


def test_statsbomb_ratings_file_exists():
    """生成的 statsbomb_elo.json 应存在且包含 ratings."""
    assert sb.OUTPUT_PATH.exists(), f"{sb.OUTPUT_PATH} not found"
    data = json.loads(sb.OUTPUT_PATH.read_text(encoding="utf-8"))
    assert "ratings" in data
    assert data["matchesApplied"] > 0
    assert len(data["ratings"]) >= 40


def test_get_statsbomb_team_elo_known_team():
    """能查到常见球队的 StatsBomb Elo."""
    rating = sb.get_statsbomb_team_elo("ARG")
    assert rating is not None
    assert 1400 < rating < 2200


def test_get_team_elo_with_source_statsbomb():
    """source=statsbomb 时返回 StatsBomb 评分."""
    rating, source, reason = _get_team_elo_with_source("ARG", source="statsbomb")
    assert rating is not None
    assert source == "statsbomb"
    assert reason is None


def test_get_team_elo_with_source_fallback():
    """StatsBomb 缺失球队应 fallback 到 Hicruben."""
    rating, source, reason = _get_team_elo_with_source("IRQ", source="statsbomb")
    assert rating is not None
    assert source == "hicruben_fallback"
    assert reason is not None
    assert "IRQ" in reason


def test_predict_match_statsbomb_source():
    """predict_match 支持 source=statsbomb."""
    result = predict_match("ARG", "BRA", source="statsbomb")
    assert "error" not in result or result.get("error") is None
    assert result["home"]["fifa_code"] == "ARG"
    assert result["away"]["fifa_code"] == "BRA"
    assert result["home"]["rating_source"] == "statsbomb"
    assert result["away"]["rating_source"] == "statsbomb"
    assert result["data_source"] == "statsbomb/open-data"
    assert "attribution" in result


def test_predict_match_statsbomb_fallback():
    """StatsBomb 缺失球队在 predict_match 中 fallback."""
    result = predict_match("IRQ", "IRN", source="statsbomb")
    assert "error" not in result or result.get("error") is None
    assert result["home"]["rating_source"] == "hicruben_fallback"
    assert result["away"]["rating_source"] == "statsbomb"
    assert result["fallback_reason"] is not None
    assert "home" in result["fallback_reason"]


def test_get_top_elo_statsbomb():
    """get_top_elo 支持 source=statsbomb."""
    rows = get_top_elo(limit=5, source="statsbomb")
    assert len(rows) == 5
    assert all("rating_source" in r for r in rows)
    assert all(r["rating_source"] == "statsbomb" for r in rows)
    # 降序
    assert rows[0]["elo"] >= rows[-1]["elo"]


def test_compare_predictions():
    """compare_predictions 同时返回两套预测."""
    result = compare_predictions("ARG", "BRA")
    assert "hicruben" in result
    assert "statsbomb" in result
    assert result["hicruben"]["home_elo"] is not None
    assert result["statsbomb"]["home_elo"] is not None
    assert result["model"] == "elo_dixon_coles_v1"
    assert "attribution" in result


# === API 集成测试 ===

@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_api_elo_ratings_source_statsbomb(client):
    """GET /api/elo/ratings?source=statsbomb 返回 200."""
    response = client.get("/api/elo/ratings?source=statsbomb")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 40
    assert all("rating_source" in r for r in data)


def test_api_elo_rating_single_source_statsbomb(client):
    """GET /api/elo/ratings/{code}?source=statsbomb 返回评分."""
    response = client.get("/api/elo/ratings/ARG?source=statsbomb")
    assert response.status_code == 200
    data = response.json()
    assert data["fifa_code"] == "ARG"
    assert data["rating_source"] == "statsbomb"


def test_api_elo_rating_fallback(client):
    """GET /api/elo/ratings/IRQ?source=statsbomb 触发 fallback."""
    response = client.get("/api/elo/ratings/IRQ?source=statsbomb")
    assert response.status_code == 200
    data = response.json()
    assert data["fifa_code"] == "IRQ"
    assert data["rating_source"] == "hicruben_fallback"
    assert data["fallback_reason"] is not None


def test_api_elo_predict_source_statsbomb(client):
    """GET /api/elo/predict/{h}/{a}?source=statsbomb 返回概率."""
    response = client.get("/api/elo/predict/ARG/BRA?source=statsbomb")
    assert response.status_code == 200
    data = response.json()
    assert "probabilities" in data
    assert data["data_source"] == "statsbomb/open-data"


def test_api_elo_predict_invalid_source(client):
    """GET /api/elo/predict 带无效 source 返回 400."""
    response = client.get("/api/elo/predict/ARG/BRA?source=invalid")
    assert response.status_code == 400


def test_api_elo_compare(client):
    """GET /api/elo/compare/{h}/{a} 返回双源对比."""
    response = client.get("/api/elo/compare/ARG/BRA")
    assert response.status_code == 200
    data = response.json()
    assert "hicruben" in data
    assert "statsbomb" in data
    assert data["hicruben"]["home_elo"] is not None
    assert data["statsbomb"]["home_elo"] is not None


def test_api_elo_predict_enhanced_source_statsbomb(client):
    """GET /api/elo/predict-enhanced 支持 source=statsbomb."""
    response = client.get("/api/elo/predict-enhanced/ARG/BRA?source=statsbomb")
    assert response.status_code == 200
    data = response.json()
    assert "v1" in data
    assert "v2" in data
    assert data["data_source"] == "statsbomb/open-data"
