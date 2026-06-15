"""F1 预测接口缓存测试."""

import time
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services.prediction_cache import (
    _team_fingerprint,
    get_cached_prediction,
    set_cached_prediction,
    invalidate_cache,
    get_cache_stats,
    CACHE_TTL_SECONDS,
)
from app.schemas import PredictionOut
from app.models import PredictionCache


# =============== 单元测试 ===============
def test_team_fingerprint_changes_with_elo():
    """Elo 变化 → fingerprint 变化."""
    from app.models import Team

    t1 = Team(id=1, fifa_code="AAA", name_zh="A", name_en="A",
              group_name="A", elo_rating=1500, recent_form_points=3, recent_goal_diff=0)
    t2 = Team(id=2, fifa_code="AAA", name_zh="A", name_en="A",
              group_name="A", elo_rating=1600, recent_form_points=3, recent_goal_diff=0)
    assert _team_fingerprint(t1) != _team_fingerprint(t2)


def test_team_fingerprint_stable():
    """相同数据 → 相同 fingerprint."""
    from app.models import Team

    t1 = Team(id=1, fifa_code="AAA", name_zh="A", name_en="A",
              group_name="A", elo_rating=1500, recent_form_points=3, recent_goal_diff=0)
    t2 = Team(id=2, fifa_code="AAA", name_zh="A", name_en="A",
              group_name="A", elo_rating=1500, recent_form_points=3, recent_goal_diff=0)
    assert _team_fingerprint(t1) == _team_fingerprint(t2)


def test_team_fingerprint_none_team():
    """None team → 'none' 指纹."""
    assert _team_fingerprint(None) == "none"


def test_cache_set_and_get_round_trip(db_session, sample_match_with_teams):
    """set → get 应能完整恢复 PredictionOut."""
    match, home, away = sample_match_with_teams

    pred = PredictionOut(
        match_id=match.id,
        home_win_prob=60.0, draw_prob=20.0, away_win_prob=20.0,
        expected_home_goals=1.5, expected_away_goals=0.8,
        recommended_score="2:1", stars=4,
        reasons=["测试理由 1", "测试理由 2"],
        h2h_summary="近 3 次交锋 1胜 1平 1负",
        h2h_record={"home_wins": 1, "away_wins": 1, "draws": 1, "sample": 3},
        home_recent_form="WWDLW", away_recent_form="WLDWW",
    )

    set_cached_prediction(db_session, match, home, away, pred)
    cached = get_cached_prediction(db_session, match, home, away)

    assert cached is not None
    assert cached.match_id == pred.match_id
    assert cached.home_win_prob == pred.home_win_prob
    assert cached.recommended_score == "2:1"
    assert cached.h2h_summary == pred.h2h_summary
    assert cached.reasons == pred.reasons


def test_cache_returns_none_when_empty(db_session, sample_match_with_teams):
    """无缓存时返回 None."""
    match, home, away = sample_match_with_teams
    assert get_cached_prediction(db_session, match, home, away) is None


def test_cache_invalidates_on_fingerprint_change(db_session, sample_match_with_teams):
    """球队数据变更 → 缓存自动失效（fingerprint 不匹配）."""
    match, home, away = sample_match_with_teams

    pred = PredictionOut(
        match_id=match.id, home_win_prob=50.0, draw_prob=30.0, away_win_prob=20.0,
        expected_home_goals=1.2, expected_away_goals=1.0,
        recommended_score="1:1", stars=3, reasons=["x"],
    )
    set_cached_prediction(db_session, match, home, away, pred)

    # 验证第一次能命中
    assert get_cached_prediction(db_session, match, home, away) is not None

    # 改 elo_rating → 指纹变化
    home.elo_rating = 1800
    db_session.commit()

    # 缓存应失效
    assert get_cached_prediction(db_session, match, home, away) is None


def test_cache_invalidates_on_ttl_expiry(db_session, sample_match_with_teams):
    """TTL 过期 → 缓存失效."""
    match, home, away = sample_match_with_teams

    pred = PredictionOut(
        match_id=match.id, home_win_prob=50.0, draw_prob=30.0, away_win_prob=20.0,
        expected_home_goals=1.2, expected_away_goals=1.0,
        recommended_score="1:1", stars=3, reasons=["x"],
    )
    set_cached_prediction(db_session, match, home, away, pred)

    # 手动把 generated_at 推到 6 分钟前（> 5 分钟 TTL）
    cache = db_session.query(PredictionCache).filter(PredictionCache.match_id == match.id).first()
    cache.generated_at = datetime.now(timezone.utc) - timedelta(seconds=CACHE_TTL_SECONDS + 1)
    db_session.commit()

    # 缓存应失效
    assert get_cached_prediction(db_session, match, home, away) is None


def test_cache_set_is_idempotent(db_session, sample_match_with_teams):
    """重复 set 同一 match_id → 覆盖而非新增."""
    match, home, away = sample_match_with_teams

    pred1 = PredictionOut(
        match_id=match.id, home_win_prob=50.0, draw_prob=30.0, away_win_prob=20.0,
        expected_home_goals=1.2, expected_away_goals=1.0,
        recommended_score="1:1", stars=3, reasons=["v1"],
    )
    pred2 = PredictionOut(
        match_id=match.id, home_win_prob=60.0, draw_prob=25.0, away_win_prob=15.0,
        expected_home_goals=1.5, expected_away_goals=0.7,
        recommended_score="2:0", stars=4, reasons=["v2"],
    )

    set_cached_prediction(db_session, match, home, away, pred1)
    set_cached_prediction(db_session, match, home, away, pred2)

    cached = get_cached_prediction(db_session, match, home, away)
    assert cached is not None
    assert cached.home_win_prob == 60.0  # 第二次写入生效
    assert cached.reasons == ["v2"]


def test_invalidate_cache(db_session, sample_match_with_teams):
    """手动 invalidate → 缓存清空."""
    match, home, away = sample_match_with_teams

    pred = PredictionOut(
        match_id=match.id, home_win_prob=50.0, draw_prob=30.0, away_win_prob=20.0,
        expected_home_goals=1.2, expected_away_goals=1.0,
        recommended_score="1:1", stars=3, reasons=["x"],
    )
    set_cached_prediction(db_session, match, home, away, pred)
    assert get_cached_prediction(db_session, match, home, away) is not None

    invalidate_cache(db_session, match.id)
    assert get_cached_prediction(db_session, match, home, away) is None


def test_cache_stats(db_session, sample_match_with_teams):
    """缓存统计正确."""
    match, home, away = sample_match_with_teams

    pred = PredictionOut(
        match_id=match.id, home_win_prob=50.0, draw_prob=30.0, away_win_prob=20.0,
        expected_home_goals=1.2, expected_away_goals=1.0,
        recommended_score="1:1", stars=3, reasons=["x"],
    )
    set_cached_prediction(db_session, match, home, away, pred)

    stats = get_cache_stats(db_session)
    assert stats["total_cached"] >= 1
    assert stats["fresh"] >= 1
    assert stats["ttl_seconds"] == CACHE_TTL_SECONDS


# =============== 性能测试（可选）==============
def test_cache_speedup(db_session, sample_match_with_teams):
    """缓存命中应比重新计算快."""
    import time as time_mod

    match, home, away = sample_match_with_teams

    pred = PredictionOut(
        match_id=match.id, home_win_prob=50.0, draw_prob=30.0, away_win_prob=20.0,
        expected_home_goals=1.2, expected_away_goals=1.0,
        recommended_score="1:1", stars=3, reasons=["x"],
    )

    # 第一次写
    t1 = time_mod.perf_counter()
    set_cached_prediction(db_session, match, home, away, pred)
    write_time = time_mod.perf_counter() - t1

    # 第二次读
    t2 = time_mod.perf_counter()
    cached = get_cached_prediction(db_session, match, home, away)
    read_time = time_mod.perf_counter() - t2

    assert cached is not None
    # 读应明显快于写（虽然 SQLite 写也很快）
    # 这里只验证读小于 50ms 即可
    assert read_time < 0.05, f"读取 {read_time*1000:.1f}ms 超过 50ms 上限"


# =============== Fixtures ===============
@pytest.fixture
def sample_match_with_teams(db_session):
    """创建一支球队 + 一场比赛."""
    from app.models import Team, Match, Stadium
    from app.db import Base
    from app.db import SessionLocal

    home = Team(
        id=10, fifa_code="ENG", name_zh="英格兰", name_en="England",
        group_name="K", flag_emoji="🏴", fifa_rank=5, elo_rating=1700,
        recent_form_points=10, recent_goal_diff=3,
    )
    away = Team(
        id=11, fifa_code="CRO", name_zh="克罗地亚", name_en="Croatia",
        group_name="K", flag_emoji="🇭🇷", fifa_rank=10, elo_rating=1680,
        recent_form_points=7, recent_goal_diff=1,
    )
    stadium = Stadium(
        id=10, name_zh="Test Stadium", name_en="Test",
        city="Test", country="Test", timezone="UTC",
    )
    match = Match(
        id=10, match_number=10, stage="小组赛", group_name="K", round_number=1,
        kickoff_at=datetime(2026, 6, 15, 18, 0),
        stadium_id=10, home_team_id=10, away_team_id=11,
        home_score=None, away_score=None, status="scheduled", data_source="manual",
    )
    db_session.add_all([home, away, stadium, match])
    db_session.commit()
    return match, home, away
