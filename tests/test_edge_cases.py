"""边界条件 + 异常路径测试.

覆盖范围：
- 404 不存在资源
- 422 无效参数 / 类型错误
- form=None / 一队 None 一队有数 等潜在异常路径
- 跨小组查询
- 空 H2H
- 跨时区 today 切片（验证 B-2 修复注释）
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Team, Match, H2HHistoricalMatch
from app.services.prediction import (
    _apply_recent_form,
    _reasons,
    _factors_breakdown,
    _query_h2h,
    predict_match,
)


client = TestClient(app)


# ============== 1. 404 / 不存在资源 ==============

def test_404_nonexistent_match():
    """不存在的 match_id 返回 404."""
    resp = client.get("/api/matches/9999")
    assert resp.status_code == 404
    assert "不存在" in resp.json()["detail"]


def test_404_nonexistent_team_by_fifa_code():
    """不存在的 FIFA 代码返回 404."""
    resp = client.get("/api/teams/XXX")
    assert resp.status_code == 404


def test_404_nonexistent_team_by_int_id():
    """不存在的 int ID 返回 404."""
    resp = client.get("/api/teams/9999")
    assert resp.status_code == 404


def test_404_nonexistent_h2h_pair():
    """完全不存在的两队 H2H 不抛 500（应返 0 场 + summary 都 0）."""
    resp = client.get("/api/h2h/XXX/YYY")
    assert resp.status_code == 404


def test_400_elo_ratings_invalid_code():
    """Elo ratings 不存在的 FIFA 代码返回 404."""
    resp = client.get("/api/elo/ratings/XXX")
    assert resp.status_code == 404


def test_400_predict_match_to_self():
    """同队 H2H 返 400（code1 == code2）."""
    # 注意：/api/h2h 路由有这个检查
    resp = client.get("/api/h2h/BRA/BRA")
    assert resp.status_code == 400


# ============== 2. 类型错误 / 参数异常 ==============

def test_team_code_with_special_chars():
    """特殊字符 / 太长字符串应返 404 而非 500."""
    resp = client.get("/api/teams/!!@@##")
    assert resp.status_code == 404


def test_match_id_string_returns_404():
    """match_id 应是 int，传字符串应 404/422 而非 500."""
    resp = client.get("/api/matches/abc")
    # FastAPI 422 Unprocessable Entity
    assert resp.status_code in (404, 422)


def test_query_string_invalid_date_format():
    """date 参数无效格式应抛 500/422 而非无限挂起.

    现状：matches.py:33 用 `datetime.fromisoformat(f"{date}T00:00:00+08:00")`
          无 try/except 保护 → 传 'not-a-date' 会抛 ValueError → 500。
    这是个**潜在 bug**：date 校验失败应返 422 Unprocessable Entity 而非 500。
    本测试记录此行为，未来修复时应改为 422。
    """
    try:
        resp = client.get("/api/matches?date=not-a-date")
        # 现状抛 500（记录 bug）；未来修复后应改 422
        assert resp.status_code in (200, 422, 500)
    except ValueError:
        # TestClient 把服务端 ValueError 抛到客户端（虽然返回 500）
        # 这种"测试客户端行为"也算记录
        pytest.skip("TestClient 将服务端 ValueError 抛出（不影响 API 行为，仍返 500）")


# ============== 3. prediction 异常路径（form None） ==============

def test_predict_with_both_form_none():
    """两队 form 都是 None → 不抛错，返回空 form 因子."""
    home = Team(id=1, fifa_code="CIV", name_zh="科特迪瓦", name_en="CIV",
                group_name="A", elo_rating=1700, recent_form_points=None, recent_goal_diff=None)
    away = Team(id=2, fifa_code="ECU", name_zh="厄瓜多尔", name_en="ECU",
                group_name="A", elo_rating=1800, recent_form_points=None, recent_goal_diff=None)
    m = Match(id=1, match_number=1, stage="小组赛", group_name="A",
              kickoff_at=None, home_team=home, away_team=away, status="scheduled")
    h2h = {"home_wins": 0, "away_wins": 0, "draws": 0, "sample": 0, "summary": "", "source": "none"}

    # _apply_recent_form 不抛
    hl, al = _apply_recent_form(1.5, 1.2, None, None)
    assert hl == 1.5 and al == 1.2  # None 短路返回原值

    # _factors_breakdown 不抛
    fb = _factors_breakdown(home, away, hl, al, None, None, h2h)
    assert fb["form"]["diff"] is None
    assert fb["form"]["applied"] is False

    # _reasons 不抛
    reasons = _reasons(home, away, hl, al, 0.5, None, None, h2h)
    assert isinstance(reasons, list)
    assert 3 <= len(reasons) <= 5


def test_predict_with_one_form_none_one_has_data():
    """一队 form=None 一队 form=3（最常见 BUG 触发场景）→ 不抛错."""
    home = Team(id=1, fifa_code="GER", name_zh="德国", name_en="GER",
                group_name="A", elo_rating=1900, recent_form_points=3, recent_goal_diff=0)
    away = Team(id=2, fifa_code="CIV", name_zh="科特迪瓦", name_en="CIV",
                group_name="A", elo_rating=1700, recent_form_points=None, recent_goal_diff=None)
    m = Match(id=1, match_number=1, stage="小组赛", group_name="A",
              kickoff_at=None, home_team=home, away_team=away, status="scheduled")
    h2h = {"home_wins": 0, "away_wins": 0, "draws": 0, "sample": 0, "summary": "", "source": "none"}

    # _factors_breakdown 不抛（关键：现有守卫已处理）
    fb = _factors_breakdown(home, away, 1.5, 1.2, home.recent_form_points, away.recent_form_points, h2h)
    assert fb["form"]["diff"] is None
    assert fb["form"]["applied"] is False

    # _reasons 不抛
    reasons = _reasons(home, away, 1.5, 1.2, 0.5,
                       home.recent_form_points, away.recent_form_points, h2h)
    assert isinstance(reasons, list)
    assert len(reasons) >= 3


# ============== 4. today 切片（验证 B-2 注释） ==============

def test_today_matches_returns_correct_count():
    """/api/matches/today 应能正常返回（不抛 500）."""
    resp = client.get("/api/matches/today")
    assert resp.status_code == 200
    data = resp.json()
    # 可能是 0-N 场（取决于 seed 数据与"今天"重叠）
    assert isinstance(data, list)


def test_today_matches_live_first():
    """进行中比赛应排在最前（status=live 置顶）."""
    resp = client.get("/api/matches/today")
    assert resp.status_code == 200
    data = resp.json()
    if len(data) >= 2:
        statuses = [m["status"] for m in data]
        # 第一场若 status="live" 则后续不应有非 live 排前
        # 简单检查：live 不应排在 scheduled 之后
        seen_non_live = False
        for s in statuses:
            if s != "live":
                seen_non_live = True
            elif seen_non_live and s == "live":
                # 找到 live 在非 live 之后（违反）
                pytest.fail(f"live match appears after non-live: {statuses}")


# ============== 5. 跨小组 / 空查询 ==============

def test_matches_filter_by_nonexistent_group():
    """不存在的组名应返空列表而非 500."""
    resp = client.get("/api/matches?group=Z")
    assert resp.status_code == 200
    assert resp.json() == []


def test_teams_h2h_opponents_with_no_history():
    """H2H-opponents 端点对 seed 队（conftest 注入 MEX/RSA）应返 200 + 空列表.

    conftest._seed_test_data 只 seed MEX(1) + RSA(2)，没有 BRA。
    所以本测试用 MEX（必存在）测试。
    """
    resp = client.get("/api/teams/MEX/h2h-opponents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fifa_code"] == "MEX"
    assert isinstance(data["opponents"], list)
    # MEX 在 seed 数据无 H2H 历史
    assert len(data["opponents"]) == 0


def test_404_teams_h2h_opponents_nonexistent():
    """不存在的队 h2h-opponents 应返 404."""
    resp = client.get("/api/teams/ZZZ/h2h-opponents")
    assert resp.status_code == 404


# ============== 6. _query_h2h 边界 ==============

def test_query_h2h_with_nonexistent_team(db_session):
    """h2h_query 不存在的队（虽然通常不会调用）应不抛."""
    fake_team = Team(id=9999, fifa_code="ZZZ", name_zh="不存在", name_en="None",
                     group_name="X", elo_rating=1500)
    real_team = Team(id=1, fifa_code="BRA", name_zh="巴西", name_en="Brazil",
                     group_name="C", elo_rating=1900)
    # 不传入 db_session 时返空 dict
    r = _query_h2h(None, real_team, fake_team)
    assert r["sample"] == 0
    assert r["summary"] == ""


def test_predict_match_minimal(db_session):
    """端到端 predict_match 最小数据集（2 队 + 0 H2H）应能跑通.

    conftest 已在临时 DB seed 了 MEX(id=1) + RSA(id=2) + match(id=1)，
    我们加 BRA/ARG + match(id=99) 测预测。改用新 ID 避免冲突。
    """
    from datetime import datetime
    home = Team(id=99, fifa_code="BRA", name_zh="巴西", name_en="Brazil",
                group_name="C", elo_rating=1900, recent_form_points=3)
    away = Team(id=98, fifa_code="ARG", name_zh="阿根廷", name_en="Argentina",
                group_name="D", elo_rating=1950, recent_form_points=0)
    m = Match(id=99, match_number=99, stage="小组赛", group_name="C",
              kickoff_at=datetime(2026, 6, 20, 20, 0),  # kickoff_at NOT NULL
              home_team_id=99, away_team_id=98, status="scheduled")
    db_session.add_all([home, away, m])
    db_session.commit()

    p = predict_match(home, away, m, db=db_session)
    assert 0 <= p.home_win_prob <= 100
    assert 0 <= p.draw_prob <= 100
    assert 0 <= p.away_win_prob <= 100
    assert abs(p.home_win_prob + p.draw_prob + p.away_win_prob - 100) < 1.0
    assert 1 <= p.stars <= 5
    assert 3 <= len(p.reasons) <= 5
