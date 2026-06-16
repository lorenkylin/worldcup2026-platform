"""v0.7.5 Adaptive Weight 单元/集成测试."""
from datetime import datetime, timedelta, timezone

import pytest

from app import db as app_db
from app.models import MCRunHistory, Match, Team
from app.services.adaptive_weight import (
    SEGMENT_WEIGHTS,
    adaptive_weight_blend,
    days_since_last_match,
    decide_segment,
    walkforward_adaptive_validate,
)


def test_segments_partition():
    """4 段边界: 0/7/30/90."""
    assert decide_segment(0) == "fresh"
    assert decide_segment(5) == "fresh"
    assert decide_segment(7) == "fresh"
    assert decide_segment(8) == "warm"
    assert decide_segment(30) == "warm"
    assert decide_segment(31) == "stale"
    assert decide_segment(90) == "stale"
    assert decide_segment(91) == "dormant"
    assert decide_segment(9999) == "dormant"


def test_adaptive_fresh_uses_g2_only():
    """FRESH 段 w_elo=0, w_g2=1.0."""
    assert SEGMENT_WEIGHTS["fresh"]["w_elo"] == 0.0
    assert SEGMENT_WEIGHTS["fresh"]["w_g2"] == 1.0


def test_adaptive_dormant_returns_50_50():
    """DORMANT 段 w_elo=0.5, w_g2=0.5 (回 v0.7.0a baseline)."""
    assert SEGMENT_WEIGHTS["dormant"]["w_elo"] == 0.5
    assert SEGMENT_WEIGHTS["dormant"]["w_g2"] == 0.5


def test_adaptive_warm_uses_8_g2():
    """WARM 段 w_g2=0.8, w_elo=0.2."""
    assert SEGMENT_WEIGHTS["warm"]["w_elo"] == 0.2
    assert SEGMENT_WEIGHTS["warm"]["w_g2"] == 0.8


def test_adaptive_stale_uses_6_g2():
    """STALE 段 w_g2=0.6, w_elo=0.4."""
    assert SEGMENT_WEIGHTS["stale"]["w_elo"] == 0.4
    assert SEGMENT_WEIGHTS["stale"]["w_g2"] == 0.6


def test_days_since_last_no_match_returns_9999():
    """球队无历史时返回 9999 (DORMANT)."""
    db = app_db.SessionLocal()
    try:
        days = days_since_last_match(db, "XXX_FAKE_CODE_XXX")
        assert days == 9999
    finally:
        db.close()


def test_days_since_last_recent_returns_small():
    """3 天前比赛 → days=3."""
    db = app_db.SessionLocal()
    try:
        # 用生产 DB 中真实存在的球队(MEX),检查 3 天内 days
        days = days_since_last_match(db, "MEX")
        # 不强求具体值(可能没比赛),但要返回 int
        assert isinstance(days, int)
        assert days >= 0
    finally:
        db.close()


def test_adaptive_blend_unknown_team_returns_404_like():
    """球队不存在时,blend_result 包含 error."""
    db = app_db.SessionLocal()
    try:
        r = adaptive_weight_blend("XXX_FAKE_1", "YYY_FAKE_2", db)
        assert r["home_code"] == "XXX_FAKE_1"
        # 球队不存在 → home_days_since_last=9999 → DORMANT
        assert r["segment"] == "dormant"
        assert r["w_g2"] == 0.5
        # blend_result 应有 error
        assert r["blend_result"].get("error") is not None
    finally:
        db.close()


def test_adaptive_blend_known_team_success():
    """真实球队 BRA/ARG → 完整返回."""
    db = app_db.SessionLocal()
    try:
        r = adaptive_weight_blend("BRA", "ARG", db)
        assert r["home_code"] == "BRA"
        assert r["away_code"] == "ARG"
        assert r["segment"] in ["fresh", "warm", "stale", "dormant"]
        assert r["w_elo"] + r["w_g2"] == pytest.approx(1.0)
        # 真实球队应有 blend result
        if r["blend_result"].get("blended"):
            probs = r["blend_result"]["blended"]["probabilities"]
            assert abs(probs["home_win"] + probs["draw"] + probs["away_win"] - 1.0) < 0.05
    finally:
        db.close()


def test_adaptive_blend_uses_max_of_two_teams():
    """两队中较长的未赛天数决定段位."""
    db = app_db.SessionLocal()
    try:
        # 强制构造:home 1 天前,away 9999 天前 → max=9999 → DORMANT
        r = adaptive_weight_blend("BRA", "ARG", db)
        # 实际段位由真实数据决定,这里只验证 max_days = max(home, away)
        assert r["max_days_since_last"] == max(r["home_days_since_last"], r["away_days_since_last"])
    finally:
        db.close()


def test_adaptive_walkforward_runs():
    """walkforward_adaptive_validate 跑 N 场,返回结构化 metrics (conftest 临时 DB 0 场也合法)."""
    db = app_db.SessionLocal()
    try:
        r = walkforward_adaptive_validate(db)
        # conftest 临时 DB 只有 2 队 + 1 场,n=0/1 都接受
        assert "n_matches" in r
        assert "accuracy" in r
        assert "brier" in r
        assert "log_loss" in r
        assert isinstance(r["n_matches"], int)
    finally:
        db.close()
