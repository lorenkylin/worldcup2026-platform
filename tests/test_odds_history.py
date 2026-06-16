"""v0.7.2.3 赔率 vs 模型走势对比 - 单元/集成测试."""
from datetime import datetime, timedelta, timezone

import pytest

from app import db as app_db
from app.models import Match, OddsSnapshot, PredictionLog, Team
from app.services.odds_api_client import (
    _decimal_to_vig_free_prob,
    build_odds_model_history,
    compute_divergence_summary,
)


@pytest.fixture
def db():
    session = app_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _ensure_match(db, match_id=90001):
    """找一个真实比赛,如不存在创建.使用 conftest 已有的 MEX(id=1)+ RSA(id=2)."""
    m = db.query(Match).filter(Match.id == match_id).first()
    if m:
        return m
    home = db.query(Team).filter(Team.id == 1).first()
    away = db.query(Team).filter(Team.id == 2).first()
    if not home or not away:
        pytest.skip("需要 conftest seed 球队 (id=1/2)")
    m = Match(
        id=match_id,
        match_number=90001,
        stage="小组赛",
        group_name="F",
        round_number=1,
        kickoff_at=datetime(2026, 6, 25, 19, 0, tzinfo=timezone.utc),
        stadium_id=1,
        home_team_id=home.id,
        away_team_id=away.id,
        status="scheduled",
        data_source="manual",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_decimal_to_vig_free_prob_basic():
    """T1: 主 2.00/平 3.50/客 4.00 → 去 vig 后三概率和=1."""
    out = _decimal_to_vig_free_prob(2.0, 3.5, 4.0)
    assert out is not None
    assert abs(out["home"] + out["draw"] + out["away"] - 1.0) < 1e-6
    # 隐含概率 home=0.5, draw=0.286, away=0.25, raw total=1.036
    # 去 vig: 0.483 / 0.276 / 0.241
    assert out["home"] > 0.4


def test_decimal_to_vig_free_prob_rejects_invalid():
    """T2: 任一字段缺失或 <=1.0 → None."""
    assert _decimal_to_vig_free_prob(None, 3.0, 4.0) is None
    assert _decimal_to_vig_free_prob(2.0, None, 4.0) is None
    assert _decimal_to_vig_free_prob(2.0, 3.0, None) is None
    assert _decimal_to_vig_free_prob(0.5, 3.0, 4.0) is None  # <=1.0


def test_build_odds_model_history_aligns_5min_window(db):
    """T3: OddsSnapshot 与 PredictionLog 5 分钟内对齐,得到 model 字段."""
    match = _ensure_match(db, match_id=90001)
    now = datetime.now(timezone.utc)

    # 清空旧数据
    db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match.id).delete()
    db.query(PredictionLog).filter(
        PredictionLog.match_id == match.id,
        PredictionLog.model_version == "blend",
    ).delete()
    db.commit()

    # 3 个 snapshot
    for i, ts in enumerate([now - timedelta(hours=2), now - timedelta(hours=1), now]):
        s = OddsSnapshot(
            match_id=match.id,
            bookmaker="avg_market",
            home_win=2.0 + i * 0.1,
            draw=3.5,
            away_win=4.0,
            snapshot_at=ts,
        )
        db.add(s)
    # 3 个 prediction_log,每个跟 snapshot 偏差 < 5min
    for i, ts in enumerate([now - timedelta(hours=2) + timedelta(seconds=30),
                              now - timedelta(hours=1) - timedelta(seconds=20),
                              now + timedelta(seconds=10)]):
        log = PredictionLog(
            match_id=match.id,
            model_version="blend",
            predicted_at=ts,
            pred_home_win=0.55 - i * 0.05,
            pred_draw=0.25,
            pred_away_win=0.20 + i * 0.05,
            predicted_outcome="H",
        )
        db.add(log)
    db.commit()

    points = build_odds_model_history(db, match.id, model="blend", hours=72)
    assert len(points) == 3
    for p in points:
        assert p["market"] is not None
        assert p["model"] is not None
        assert p["model"]["home"] > 0


def test_build_odds_model_history_no_match_returns_empty(db):
    """T4: 比赛不存在 → 空列表(端点会 404)."""
    points = build_odds_model_history(db, match_id=99999999, model="blend", hours=72)
    assert points == []


def test_build_odds_model_history_outside_window_skipped(db):
    """T5: 超出 hours 窗口的 snapshot 不会进入结果."""
    match = _ensure_match(db, match_id=90001)
    now = datetime.now(timezone.utc)

    db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match.id).delete()
    db.commit()

    # 5h 前 + 1h 前
    s1 = OddsSnapshot(
        match_id=match.id, bookmaker="avg_market",
        home_win=2.0, draw=3.5, away_win=4.0,
        snapshot_at=now - timedelta(hours=5),
    )
    s2 = OddsSnapshot(
        match_id=match.id, bookmaker="avg_market",
        home_win=2.0, draw=3.5, away_win=4.0,
        snapshot_at=now - timedelta(hours=1),
    )
    db.add_all([s1, s2])
    db.commit()

    points = build_odds_model_history(db, match.id, model="blend", hours=2)
    assert len(points) == 1


def test_build_odds_model_history_missing_odds_yields_none_market(db):
    """T6: snapshot 缺 home_win/draw/away_win → market=None(该点无效)."""
    match = _ensure_match(db, match_id=90001)
    now = datetime.now(timezone.utc)

    db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match.id).delete()
    db.commit()

    s = OddsSnapshot(
        match_id=match.id, bookmaker="avg_market",
        home_win=None, draw=3.5, away_win=4.0,
        snapshot_at=now,
    )
    db.add(s)
    db.commit()

    points = build_odds_model_history(db, match.id, model="blend", hours=24)
    assert len(points) == 1
    assert points[0]["market"] is None


def test_divergence_summary_basic():
    """T7: 3 个分歧点 → summary 正确计算 home/draw/away diff_max + favored."""
    points = [
        {"ts": "2026-06-16T10:00:00+00:00",
         "market": {"home": 0.6, "draw": 0.25, "away": 0.15},
         "model":  {"home": 0.5, "draw": 0.3,  "away": 0.2}},
        {"ts": "2026-06-16T11:00:00+00:00",
         "market": {"home": 0.65, "draw": 0.2, "away": 0.15},
         "model":  {"home": 0.55, "draw": 0.25, "away": 0.2}},
        {"ts": "2026-06-16T12:00:00+00:00",
         "market": {"home": 0.55, "draw": 0.25, "away": 0.2},
         "model":  {"home": 0.5, "draw": 0.3,  "away": 0.2}},
    ]
    summary = compute_divergence_summary(points)
    # home diffs: 0.1, 0.1, 0.05 → max 0.1
    assert summary["home_diff_max"] == pytest.approx(0.1)
    # draw diffs: 0.05, 0.05, 0.05 → max 0.05
    assert summary["draw_diff_max"] == pytest.approx(0.05)
    # away diffs: 0.05, 0.05, 0.0 → max 0.05
    assert summary["away_diff_max"] == pytest.approx(0.05)
    # market home 一直 > model home,avg signed = (0.1+0.1+0.05)/3 = 0.083 > 0.05 → favored = home
    assert summary["market_favored"] == "home"


def test_divergence_summary_empty_returns_defaults():
    """T8: 空 points → 默认值 + 不会 raise."""
    s = compute_divergence_summary([])
    assert s["home_diff_max"] == 0.0
    assert s["draw_diff_max"] == 0.0
    assert s["away_diff_max"] == 0.0
    assert s["market_favored"] == "home"
