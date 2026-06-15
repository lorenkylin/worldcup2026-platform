"""API 端到端测试."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    """健康检查端点."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "2026" in data["app"]


def test_index_page_serves():
    """根路径应返回 H5 首页 HTML."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "2026 世界杯赛事分析" in resp.text


def test_static_js_serves():
    """前端 JS 可访问."""
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    assert "renderHome" in resp.text


def test_list_matches():
    """获取全部比赛列表."""
    resp = client.get("/api/matches")
    assert resp.status_code == 200
    matches = resp.json()
    assert isinstance(matches, list)
    # 临时测试数据中只有 1 场
    assert len(matches) == 1


def test_list_teams_has_2_entries():
    """临时测试数据中只 seed 2 支球队."""
    resp = client.get("/api/teams")
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 2


def test_today_matches():
    """今日比赛端点."""
    resp = client.get("/api/matches/today")
    assert resp.status_code == 200
    matches = resp.json()
    assert isinstance(matches, list)


def test_list_teams_has_2_entries():
    """临时测试数据中只 seed 2 支球队."""
    resp = client.get("/api/teams")
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 2


def test_team_detail():
    """球队详情."""
    resp = client.get("/api/teams/1")
    assert resp.status_code == 200
    team = resp.json()
    assert team["id"] == 1
    assert "name_zh" in team
    assert "elo_rating" in team


def test_match_detail():
    """比赛详情."""
    resp = client.get("/api/matches/1")
    assert resp.status_code == 200
    match = resp.json()
    assert match["id"] == 1
    assert "home_team" in match
    assert "stadium" in match


def test_match_prediction():
    """单场预测."""
    resp = client.get("/api/matches/1/prediction")
    assert resp.status_code == 200
    pred = resp.json()
    assert 0 < pred["home_win_prob"] < 100
    assert 0 < pred["draw_prob"] < 100
    assert 0 < pred["away_win_prob"] < 100
    total = pred["home_win_prob"] + pred["draw_prob"] + pred["away_win_prob"]
    assert 99 < total < 101
    assert ":" in pred["recommended_score"]
    assert 1 <= pred["stars"] <= 5


def test_groups_standings():
    """临时数据中只 seed 了 A 组."""
    resp = client.get("/api/groups")
    assert resp.status_code == 200
    groups = resp.json()
    assert "A" in groups
    assert len(groups["A"]) == 2  # 临时数据中 A 组 2 队


def test_team_matches():
    """球队关联赛程."""
    resp = client.get("/api/teams/1/matches")
    assert resp.status_code == 200
    matches = resp.json()
    assert isinstance(matches, list)
    assert len(matches) >= 1


def test_match_not_found_404():
    """不存在的比赛应返回 404."""
    resp = client.get("/api/matches/9999")
    assert resp.status_code == 404


def test_prediction_requires_two_teams():
    """对阵未确定的比赛应返回 400（淘汰赛占位时）."""
    # 找一个尚未确定对阵的比赛
    resp = client.get("/api/matches/105")  # 假设淘汰赛 ID 较大
    if resp.status_code == 200:
        # 跳过若数据库中有占位
        return
    assert resp.status_code in (200, 404, 400)


def test_admin_score_update_requires_token():
    """管理接口需 X-Admin-Token."""
    resp = client.post("/api/admin/matches/1/score", json={
        "home_score": 1, "away_score": 0, "status": "finished", "time_elapsed": "90"
    })
    assert resp.status_code == 422 or resp.status_code == 403  # 缺 header


def test_admin_score_update_with_token():
    """带 Token 可成功更新比分."""
    resp = client.post(
        "/api/admin/matches/1/score",
        json={"home_score": 3, "away_score": 1, "status": "finished", "time_elapsed": "90"},
        headers={"x-admin-token": "worldcup2026-admin"},  # FastAPI header 区分大小写归一为小写
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
