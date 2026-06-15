"""Bracket 淘汰赛对阵逻辑测试."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Match, Standing, Team
from app.services.bracket_logic import (
    BracketSlot,
    compute_group_standings,
    rank_third_place_teams,
    resolve_r32_matchups,
    update_knockout_matches,
    rebuild_bracket,
    build_bracket,
    should_auto_rebuild,
    R32_MATCHUPS,
)


def _seed_minimal_teams(db) -> None:
    """写入 12 组 × 4 队的测试球队（id 由 DB 自增，避免与 conftest seed 冲突）."""
    groups = "ABCDEFGHIJKL"
    teams = []
    for idx, group in enumerate(groups):
        for rank in range(4):
            teams.append(
                Team(
                    fifa_code=f"{group}{rank+1}",
                    name_zh=f"{group}组第{rank+1}",
                    name_en=f"Team {group}{rank+1}",
                    group_name=group,
                    flag_emoji="🏳️",
                    elo_rating=1500 + (12 - idx * 4 - rank) * 10,  # 差异化 Elo
                )
            )
    db.add_all(teams)
    db.commit()


def _seed_standings(db, standings_config) -> None:
    """按配置写入积分榜.

    standings_config: {group_name: [(points, gf, ga), ...]}
    """
    team_map = {t.fifa_code: t for t in db.query(Team).all()}
    rows = []
    for group, configs in standings_config.items():
        for idx, (points, gf, ga) in enumerate(configs):
            code = f"{group}{idx+1}"
            team = team_map[code]
            won = points // 3
            drawn = (points % 3) // 1
            lost = 2 - won - drawn  # 默认 3 场赛制简化
            rows.append(
                Standing(
                    group_name=group,
                    team_id=team.id,
                    played=3,
                    won=won,
                    drawn=drawn,
                    lost=lost,
                    goals_for=gf,
                    goals_against=ga,
                    points=points,
                )
            )
    db.add_all(rows)
    db.commit()


def _seed_knockout_placeholders(db) -> None:
    """写入 Match 1-72 小组赛占位 + Match 73-104 淘汰赛占位记录."""
    matches = []
    # 小组赛：12 组 × 6 场 = 72 场
    groups = "ABCDEFGHIJKL"
    match_num = 1
    for group in groups:
        for _ in range(6):
            matches.append(
                Match(
                    match_number=match_num,
                    stage="小组赛",
                    group_name=group,
                    round_number=1,
                    kickoff_at=datetime(2026, 6, 11, 0, 0),
                    home_team_placeholder=f"G{group}H",
                    away_team_placeholder=f"G{group}A",
                    status="scheduled",
                )
            )
            match_num += 1
    # 淘汰赛
    for num in range(73, 105):
        stage = "16强" if num <= 88 else ("8强" if num <= 96 else ("半决赛" if num <= 102 else ("季军" if num == 103 else "决赛")))
        matches.append(
            Match(
                match_number=num,
                stage=stage,
                group_name=None,
                round_number=0,
                kickoff_at=datetime(2026, 6, 28, 0, 0),
                home_team_placeholder="TBD",
                away_team_placeholder="TBD",
                status="scheduled",
            )
        )
    db.add_all(matches)
    db.commit()


def _seed_group_matches_finished(db) -> None:
    """把 match_number 1-72 标为已结束（用于 group_stage_finished 测试）."""
    for m in db.query(Match).filter(Match.match_number <= 72).all():
        m.status = "finished"
    db.commit()


def _full_seed(db, standings_config) -> None:
    # 清空 conftest 注入的 seed 数据，保证 Bracket 测试自包含
    db.query(Match).delete()
    db.query(Standing).delete()
    db.query(Team).delete()
    db.commit()
    _seed_minimal_teams(db)
    _seed_standings(db, standings_config)
    _seed_knockout_placeholders(db)


# === 单元测试 ===


def test_compute_group_standings_sorts_by_points_goal_diff_goals(db_session):
    """小组排名应遵循 积分 > 净胜球 > 进球."""
    _full_seed(db_session, {
        "A": [(9, 6, 1), (4, 3, 3), (4, 2, 3), (0, 1, 5)],
    })
    standings = compute_group_standings(db_session)

    group_a = standings["A"]
    assert len(group_a) == 4
    assert group_a[0].team.fifa_code == "A1"
    assert group_a[0].points == 9
    # A2 与 A3 同分 4 分，A2 净胜球 0 > A3 净胜球 -1
    assert group_a[1].team.fifa_code == "A2"
    assert group_a[2].team.fifa_code == "A3"


def test_rank_third_place_teams_top_eight(db_session):
    """12 个小组第三应取前 8."""
    config = {
        # 第三名为 X3
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "C": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "D": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "E": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "F": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "G": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "H": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "I": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "J": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "K": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "L": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    }
    _full_seed(db_session, config)
    standings = compute_group_standings(db_session)
    thirds = rank_third_place_teams(standings)

    assert len(thirds) == 8
    # 所有第三同分，按净胜球/进球无法区分，但函数应稳定返回 8 个
    codes = {t.team.fifa_code for t in thirds}
    assert codes == {f"{g}3" for g in "ABCDEFGH"}


def test_resolve_r32_matchups_returns_sixteen_slots(db_session):
    """R32 应生成 16 个对阵槽位."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "C": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "D": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "E": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "F": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "G": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "H": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "I": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "J": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "K": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "L": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    standings = compute_group_standings(db_session)
    thirds = rank_third_place_teams(standings)
    slots = resolve_r32_matchups(standings, thirds)

    assert len(slots) == 16
    # M73 固定为 2A vs 2B
    m73 = next(s for s in slots if s.match_number == 73)
    assert m73.home_team.fifa_code == "A2"
    assert m73.away_team.fifa_code == "B2"


def test_update_knockout_matches_persists_to_db(db_session):
    """对阵结果应正确写回 matches 表."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    # 只给 A/B 两组数据时，最佳第三不足 8 个，部分槽位会为空
    standings = compute_group_standings(db_session)
    thirds = rank_third_place_teams(standings)
    slots = resolve_r32_matchups(standings, thirds)
    result = update_knockout_matches(db_session, slots)

    assert result["updated"] == 16
    m73 = db_session.query(Match).filter(Match.match_number == 73).first()
    assert m73.home_team.fifa_code == "A2"
    assert m73.away_team.fifa_code == "B2"


def test_rebuild_bracket_returns_ok(db_session):
    """rebuild_bracket 应返回成功摘要."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    result = rebuild_bracket(db_session)
    assert result["ok"] is True
    assert result["updated_matches"] == 16


def test_build_bracket_group_stage_not_finished(db_session):
    """小组赛未结束时 group_stage_finished 应为 false."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    bracket = build_bracket(db_session)
    assert bracket["group_stage_finished"] is False
    assert "rounds" in bracket
    assert len(bracket["rounds"]["r32"]) == 16


def test_build_bracket_group_stage_finished(db_session):
    """小组赛全部结束后 group_stage_finished 应为 true."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    _seed_group_matches_finished(db_session)
    bracket = build_bracket(db_session)
    assert bracket["group_stage_finished"] is True


def test_r32_matchups_table_complete():
    """R32_MATCHUPS 应包含 73-88 共 16 场."""
    assert len(R32_MATCHUPS) == 16
    numbers = {int(m["match_number"]) for m in R32_MATCHUPS}
    assert numbers == set(range(73, 89))


# === API 集成测试 ===


def test_api_bracket_returns_structure(db_session, client):
    """GET /api/bracket 应返回标准结构."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    response = client.get("/api/bracket")
    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data
    assert "group_stage_finished" in data
    assert "rounds" in data
    assert len(data["rounds"]["r32"]) == 16


def test_api_bracket_prediction_when_both_teams_known(db_session, client):
    """双方球队确定时，节点应包含 Elo 预测."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    response = client.get("/api/bracket")
    data = response.json()
    m73 = next(m for m in data["rounds"]["r32"] if m["match_number"] == 73)
    assert m73["home"]["team"] is not None
    assert m73["away"]["team"] is not None
    assert "prediction" in m73
    assert 0 <= m73["prediction"]["home_win"] <= 1


def test_api_admin_bracket_rebuild_requires_token(db_session, client):
    """POST /api/admin/bracket/rebuild 需要 admin token."""
    response = client.post("/api/admin/bracket/rebuild")
    assert response.status_code in (403, 422)  # 缺 header 时 FastAPI 可能返回 422


def test_api_admin_bracket_rebuild_with_token(db_session, client):
    """携带正确 token 可触发重建."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    response = client.post(
        "/api/admin/bracket/rebuild",
        headers={"X-Admin-Token": "worldcup2026-admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["updated_matches"] == 16


# === 自动 rebuild 测试 ===


def test_should_auto_rebuild_false_when_group_stage_not_finished(db_session):
    """小组赛未结束时，不应自动 rebuild."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    assert should_auto_rebuild(db_session) is False


def test_should_auto_rebuild_true_when_finished_but_r32_empty(db_session):
    """小组赛结束且 R32 尚未落位时，应自动 rebuild."""
    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    _seed_group_matches_finished(db_session)
    assert should_auto_rebuild(db_session) is True


def test_should_auto_rebuild_false_after_rebuild(db_session):
    """R32 全部落位后，不应再自动 rebuild."""
    # 构造 12 组积分，让最佳 8 个第三为 A/B/C/D/E/F/I/J（与 2026 Annex C 槽位兼容），
    # 确保简化贪心策略能填满 8 个第三槽位。
    config = {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "C": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "D": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "E": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "F": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        # G/H 第三 2 分，排不进前 8
        "G": [(9, 3, 0), (6, 2, 1), (2, 1, 2), (0, 0, 3)],
        "H": [(9, 3, 0), (6, 2, 1), (2, 1, 2), (0, 0, 3)],
        "I": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "J": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        # K/L 第三 0 分
        "K": [(9, 3, 0), (6, 2, 1), (0, 0, 2), (0, 0, 3)],
        "L": [(9, 3, 0), (6, 2, 1), (0, 0, 2), (0, 0, 3)],
    }
    _full_seed(db_session, config)
    _seed_group_matches_finished(db_session)
    result = rebuild_bracket(db_session)
    assert result["updated_matches"] == 16
    # 确认 16 场 R32 全部落位
    r32 = db_session.query(Match).filter(Match.match_number >= 73, Match.match_number <= 88).all()
    assert all(m.home_team_id is not None and m.away_team_id is not None for m in r32)
    assert should_auto_rebuild(db_session) is False


def test_job_bracket_auto_rebuild_triggers_when_ready(db_session):
    """调度任务在条件满足时应执行 rebuild."""
    from app.services.scheduler import _job_bracket_auto_rebuild

    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
        "B": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    _seed_group_matches_finished(db_session)

    calls = []
    original_rebuild = rebuild_bracket

    def _mock_rebuild(db):
        calls.append("rebuild")
        return original_rebuild(db)

    # 通过 monkeypatch 方式替换局部引用
    import app.services.scheduler as scheduler_mod
    import app.services.bracket_logic as bracket_mod

    old_should = bracket_mod.should_auto_rebuild
    old_rebuild = bracket_mod.rebuild_bracket
    try:
        bracket_mod.should_auto_rebuild = should_auto_rebuild
        bracket_mod.rebuild_bracket = _mock_rebuild
        scheduler_mod._job_bracket_auto_rebuild(lambda: db_session)
    finally:
        bracket_mod.should_auto_rebuild = old_should
        bracket_mod.rebuild_bracket = old_rebuild

    assert len(calls) == 1


def test_job_bracket_auto_rebuild_skips_when_not_ready(db_session):
    """调度任务在条件不满足时不应执行 rebuild."""
    from app.services.scheduler import _job_bracket_auto_rebuild

    _full_seed(db_session, {
        "A": [(9, 3, 0), (6, 2, 1), (3, 1, 2), (0, 0, 3)],
    })
    # 小组赛未结束

    calls = []
    original_rebuild = rebuild_bracket

    def _mock_rebuild(db):
        calls.append("rebuild")
        return original_rebuild(db)

    import app.services.scheduler as scheduler_mod
    import app.services.bracket_logic as bracket_mod

    old_should = bracket_mod.should_auto_rebuild
    old_rebuild = bracket_mod.rebuild_bracket
    try:
        bracket_mod.should_auto_rebuild = should_auto_rebuild
        bracket_mod.rebuild_bracket = _mock_rebuild
        scheduler_mod._job_bracket_auto_rebuild(lambda: db_session)
    finally:
        bracket_mod.should_auto_rebuild = old_should
        bracket_mod.rebuild_bracket = old_rebuild

    assert len(calls) == 0


# 需要一个 client fixture（如果 conftest 没有提供）
@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)
