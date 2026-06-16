"""Admin 赔率录入 API 测试.

覆盖:
  - 单条录入 (POST /api/admin/odds)
  - 鉴权失败 (无 Token / 错误 Token)
  - 比赛不存在
  - 赔率超出范围
  - 覆盖式更新(同 match_id+bookmaker)
  - 批量录入 (POST /api/admin/odds/batch)
  - 删除 (DELETE /api/admin/odds/{id})
"""
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
# 从 .env 读取（与生产保持一致）
from app.config import settings
ADMIN_TOKEN = settings.admin_token
HEADERS = {"X-Admin-Token": ADMIN_TOKEN}


def test_create_odds_basic():
    """基础单条录入."""
    response = client.post("/api/admin/odds", headers=HEADERS, json={
        "match_id": 1,
        "bookmaker": "bet365",
        "home_win": 2.10,
        "draw": 3.40,
        "away_win": 3.60,
        "over_2_5": 1.95,
        "under_2_5": 1.85,
        "source": "manual",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["match_id"] == 1
    assert data["bookmaker"] == "bet365"
    assert data["home_win"] == 2.10
    assert data["draw"] == 3.40


def test_create_odds_unauthorized():
    """无 Token 鉴权失败."""
    response = client.post("/api/admin/odds", json={
        "match_id": 1, "home_win": 2.0, "draw": 3.0, "away_win": 4.0,
    })
    assert response.status_code == 422  # Header 必填


def test_create_odds_wrong_token():
    """错误 Token → 403."""
    response = client.post(
        "/api/admin/odds",
        headers={"X-Admin-Token": "wrong-token"},
        json={"match_id": 1, "home_win": 2.0, "draw": 3.0, "away_win": 4.0},
    )
    assert response.status_code == 403
    assert "管理员 Token 无效" in response.json()["detail"]


def test_create_odds_match_not_found():
    """match_id 不存在 → 404."""
    response = client.post("/api/admin/odds", headers=HEADERS, json={
        "match_id": 99999,
        "home_win": 2.0, "draw": 3.0, "away_win": 4.0,
    })
    assert response.status_code == 404


def test_create_odds_invalid_range_low():
    """赔率 < 1.01 → 400."""
    response = client.post("/api/admin/odds", headers=HEADERS, json={
        "match_id": 1,
        "home_win": 1.0,  # 边界外
        "draw": 3.0, "away_win": 4.0,
    })
    assert response.status_code == 400


def test_create_odds_invalid_range_high():
    """赔率 > 1000 → 400."""
    response = client.post("/api/admin/odds", headers=HEADERS, json={
        "match_id": 1,
        "home_win": 2000.0,  # 边界外
        "draw": 3.0, "away_win": 4.0,
    })
    assert response.status_code == 400


def test_create_odds_overwrite():
    """同 match_id + bookmaker → 覆盖更新."""
    payload = {
        "match_id": 1, "bookmaker": "pinnacle",
        "home_win": 2.10, "draw": 3.40, "away_win": 3.60,
    }
    # 第一次录入
    r1 = client.post("/api/admin/odds", headers=HEADERS, json=payload)
    assert r1.status_code == 200
    odds_id_1 = r1.json()["id"]

    # 第二次同 bookmaker 录入(更新)
    payload2 = {**payload, "home_win": 1.95, "draw": 3.50, "away_win": 3.70}
    r2 = client.post("/api/admin/odds", headers=HEADERS, json=payload2)
    assert r2.status_code == 200
    odds_id_2 = r2.json()["id"]

    # ID 应相同(覆盖)
    assert odds_id_1 == odds_id_2
    assert r2.json()["home_win"] == 1.95


def test_create_odds_batch():
    """批量录入."""
    response = client.post("/api/admin/odds/batch", headers=HEADERS, json={
        "items": [
            {"match_id": 1, "bookmaker": "bet365", "home_win": 2.0, "draw": 3.0, "away_win": 4.0},
            {"match_id": 1, "bookmaker": "pinnacle", "home_win": 2.05, "draw": 3.05, "away_win": 3.95},
            {"match_id": 99999, "bookmaker": "bet365", "home_win": 2.0, "draw": 3.0, "away_win": 4.0},  # 失败
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    # 至少 2 条成功(inserted/updated 任意)
    assert (data["inserted"] + data["updated"]) >= 2
    assert len(data["failed"]) >= 1
    assert data["failed"][0]["match_id"] == 99999


def test_create_odds_batch_empty():
    """空列表 → total=0."""
    response = client.post("/api/admin/odds/batch", headers=HEADERS, json={"items": []})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["inserted"] == 0


def test_create_odds_batch_unauthorized():
    """批量无 Token."""
    response = client.post("/api/admin/odds/batch", json={
        "items": [{"match_id": 1, "home_win": 2.0, "draw": 3.0, "away_win": 4.0}],
    })
    assert response.status_code == 422


def test_delete_odds():
    """删除单条."""
    # 先录入
    r1 = client.post("/api/admin/odds", headers=HEADERS, json={
        "match_id": 1, "bookmaker": "test_delete",
        "home_win": 2.0, "draw": 3.0, "away_win": 4.0,
    })
    odds_id = r1.json()["id"]

    # 删除
    r2 = client.delete(f"/api/admin/odds/{odds_id}", headers=HEADERS)
    assert r2.status_code == 200
    assert "已删除" in r2.json()["message"]


def test_delete_odds_not_found():
    """删除不存在的 ID."""
    response = client.delete("/api/admin/odds/99999", headers=HEADERS)
    assert response.status_code == 404


def test_delete_odds_unauthorized():
    """删除无 Token."""
    response = client.delete("/api/admin/odds/1")
    assert response.status_code == 422
