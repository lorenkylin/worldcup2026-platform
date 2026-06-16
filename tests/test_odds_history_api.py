"""赔率历史 API 集成测试（v0.5.1）.

覆盖:
  GET /api/matches/{id}/odds/history
    - 404 (比赛不存在)
    - 200 + has_history=False (比赛存在但无 snapshot)
    - 200 + 多公司多时间点
    - 200 + bookmaker 过滤
    - 时间升序排列
    - null 字段处理

注意:
  - 用 dependency_overrides 让 FastAPI get_db 使用 conftest 提供的临时 DB
  - 用 late binding 通过 app_db.SessionLocal() 动态获取最新的 SessionLocal(避免缓存 module-level 引用)
  - 测试后清空 app.dependency_overrides 避免污染其他测试模块
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db as app_db
from app.db import get_db
from app.main import app
from app.models import Match, OddsSnapshot


def _override_get_db():
    """每次调用时获取最新的 SessionLocal(避免 module-level 缓存)."""
    session = app_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _setup_overrides():
    """每个测试前设置 override,测试后清空避免污染其他测试模块."""
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _new_session():
    """获取新的测试 session."""
    return app_db.SessionLocal()


# ============ 测试 ============


def test_404_for_nonexistent_match(client):
    """不存在的 match → 404."""
    r = client.get("/api/matches/9999/odds/history")
    assert r.status_code == 404
    assert "不存在" in r.json()["detail"]


def test_empty_history_for_match_without_snapshots(client):
    """比赛存在但无 snapshot → has_history=False + 空 series."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        db.commit()
    finally:
        db.close()

    r = client.get("/api/matches/1/odds/history")
    assert r.status_code == 200
    data = r.json()
    assert data["has_history"] is False
    assert data["count"] == 0
    assert data["bookmakers"] == []
    assert data["series"] == {}


def test_history_with_multiple_bookmakers_and_timepoints(client):
    """多公司多时间点 → 返回正确结构."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        base = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        for bm in ["bet365", "pinnacle", "williamhill"]:
            for h in [24, 6]:
                db.add(
                    OddsSnapshot(
                        match_id=1,
                        bookmaker=bm,
                        home_win=2.0,
                        draw=3.4,
                        away_win=4.5,
                        snapshot_at=base - timedelta(hours=h),
                        source="manual_test",
                    )
                )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/matches/1/odds/history")
    data = r.json()
    assert data["has_history"] is True
    assert data["count"] == 6
    assert set(data["bookmakers"]) == {"bet365", "pinnacle", "williamhill"}
    for bm in data["bookmakers"]:
        assert len(data["series"][bm]) == 2
        first = data["series"][bm][0]
        assert "t" in first
        assert "home_win" in first
        assert "draw" in first
        assert "away_win" in first
        assert "source" in first

    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        db.commit()
    finally:
        db.close()


def test_history_bookmaker_filter(client):
    """?bookmaker=bet365 只返回 bet365 的 series."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        for bm in ["bet365", "pinnacle"]:
            db.add(
                OddsSnapshot(
                    match_id=1,
                    bookmaker=bm,
                    home_win=2.0,
                    draw=3.4,
                    away_win=4.5,
                    source="manual_test",
                )
            )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/matches/1/odds/history?bookmaker=bet365")
    data = r.json()
    assert data["bookmakers"] == ["bet365"]
    assert "bet365" in data["series"]
    assert "pinnacle" not in data["series"]

    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        db.commit()
    finally:
        db.close()


def test_history_sorted_ascending_by_time(client):
    """同一 bookmaker 多个 snapshot 时按时间升序."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        base = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        for hours_ago in [0, 24, 12, 6]:
            db.add(
                OddsSnapshot(
                    match_id=1,
                    bookmaker="testbook",
                    home_win=2.0,
                    draw=3.4,
                    away_win=4.5,
                    snapshot_at=base - timedelta(hours=hours_ago),
                    source="manual_test",
                )
            )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/matches/1/odds/history?bookmaker=testbook")
    data = r.json()
    assert data["count"] == 4
    series = data["series"]["testbook"]
    timestamps = [s["t"] for s in series]
    assert timestamps == sorted(timestamps)

    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(
            OddsSnapshot.match_id == 1, OddsSnapshot.bookmaker == "testbook"
        ).delete()
        db.commit()
    finally:
        db.close()


def test_history_handles_null_odds(client):
    """部分字段为 None 的 snapshot 也能正确返回(前端需渲染 N/A)."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(OddsSnapshot.match_id == 1).delete()
        db.add(
            OddsSnapshot(
                match_id=1,
                bookmaker="partialbook",
                home_win=2.0,
                draw=None,
                away_win=4.0,
                over_2_5=1.8,
                under_2_5=None,
                source="manual_partial",
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/matches/1/odds/history?bookmaker=partialbook")
    data = r.json()
    snap = data["series"]["partialbook"][0]
    assert snap["home_win"] == 2.0
    assert snap["draw"] is None
    assert snap["away_win"] == 4.0
    assert snap["over_2_5"] == 1.8
    assert snap["under_2_5"] is None

    db = _new_session()
    try:
        db.query(OddsSnapshot).filter(
            OddsSnapshot.match_id == 1, OddsSnapshot.bookmaker == "partialbook"
        ).delete()
        db.commit()
    finally:
        db.close()
