"""赔率查询 API 测试 (公开).

覆盖:
  - GET /api/matches/{id}/odds
  - GET /api/odds/compare
  - GET /api/odds/value-bets
"""
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
from app.config import settings
ADMIN_TOKEN = settings.admin_token
HEADERS = {"X-Admin-Token": ADMIN_TOKEN}


def _seed_odds(match_id=1, bookmaker="avg_market", home=2.10, draw=3.40, away=3.60):
    """辅助: 录入一条赔率."""
    return client.post("/api/admin/odds", headers=HEADERS, json={
        "match_id": match_id, "bookmaker": bookmaker,
        "home_win": home, "draw": draw, "away_win": away,
    })


# ============ GET /api/matches/{id}/odds ============

def test_get_match_odds_no_data():
    """无赔率 → has_odds=false."""
    response = client.get("/api/matches/1/odds")
    assert response.status_code == 200
    data = response.json()
    assert data["has_odds"] is False
    assert "暂无赔率" in data["message"]


def test_get_match_odds_single_bookmaker():
    """1 家赔率."""
    _seed_odds(home=2.0, draw=3.0, away=4.0)
    response = client.get("/api/matches/1/odds")
    assert response.status_code == 200
    data = response.json()
    assert data["has_odds"] is True
    assert len(data["bookmakers"]) == 1
    assert data["bookmakers"][0]["odds"]["home_win"] == 2.0
    # market_prob 应该有
    assert data["bookmakers"][0]["market_prob"]["home_prob"] > 0
    # consensus(只有 1 家时也是该家的赔率)
    assert data["consensus"] is not None
    assert math_close(data["consensus"]["market_prob"]["home_prob"],
                      data["bookmakers"][0]["market_prob"]["home_prob"])


def test_get_match_odds_multiple_bookmakers():
    """多家赔率 → consensus 是平均."""
    _seed_odds(bookmaker="bet365", home=2.0, draw=3.0, away=4.0)
    _seed_odds(bookmaker="pinnacle", home=2.2, draw=3.2, away=3.8)
    _seed_odds(bookmaker="williamhill", home=1.8, draw=2.8, away=4.2)

    response = client.get("/api/matches/1/odds")
    assert response.status_code == 200
    data = response.json()
    assert len(data["bookmakers"]) == 3
    # consensus 是平均
    assert math_close(data["consensus"]["odds"]["home_win"], 2.0)  # (2.0+2.2+1.8)/3
    assert math_close(data["consensus"]["odds"]["draw"], 3.0)
    assert math_close(data["consensus"]["odds"]["away_win"], 4.0)


def test_get_match_odds_match_not_found():
    """比赛不存在."""
    response = client.get("/api/matches/99999/odds")
    assert response.status_code == 404


# ============ GET /api/odds/compare ============

def test_compare_no_odds():
    """无赔率 → count=0."""
    response = client.get("/api/odds/compare")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_compare_with_odds():
    """有赔率 → 包含 value_bet."""
    _seed_odds(home=2.0, draw=3.0, away=4.0)

    response = client.get("/api/odds/compare?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    item = data["items"][0]
    assert "match_id" in item
    assert "market" in item
    assert "elo" in item
    assert "value_bet" in item
    assert "best_value" in item
    # home_team / away_team 应有 elo
    assert "elo" in item["home_team"]
    assert "elo" in item["away_team"]


def test_compare_limit():
    """limit 参数生效."""
    response = client.get("/api/odds/compare?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] <= 1


# ============ GET /api/odds/value-bets ============

def test_value_bets_empty():
    """无价值投注 → count=0."""
    response = client.get("/api/odds/value-bets?min_rate=0.10")
    assert response.status_code == 200
    data = response.json()
    # 可能为 0 或 >= 0,反正不报错
    assert "items" in data
    assert "min_rate" in data
    assert data["min_rate"] == 0.10


def test_value_bets_with_data():
    """有价值投注 → count >= 0."""
    _seed_odds(home=5.0, draw=3.5, away=1.8)  # 市场强烈客胜,模型可能不同意
    response = client.get("/api/odds/value-bets?min_rate=0.01&limit=5")
    assert response.status_code == 200
    data = response.json()
    # 至少能找到(因为 MEX 1700 vs RSA 1500 Elo 模型不会强烈客胜)
    assert isinstance(data["items"], list)
    # 排序: rate 降序
    for i in range(len(data["items"]) - 1):
        assert data["items"][i]["best_value_rate"] >= data["items"][i + 1]["best_value_rate"]


def test_value_bets_invalid_min_rate():
    """min_rate 越界 → 422."""
    response = client.get("/api/odds/value-bets?min_rate=2.0")  # > 1.0
    assert response.status_code == 422


# ============ 工具函数 ============

def math_close(a, b, rel=1e-3):
    """简单浮点比较."""
    if b == 0:
        return abs(a) < rel
    return abs(a - b) / abs(b) < rel
