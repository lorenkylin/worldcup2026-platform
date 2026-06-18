"""v0.5.1 6h 周期刷新服务集成测试.

覆盖:
  take_odds_snapshots:
    - 给所有现有 MatchOdds 追加 snapshot
    - 同一 2s 窗口内的二次执行幂等(去重)
  refresh_match_metadata_from_football_data:
    - enabled=False → skipped
    - 无 api_key → skipped
    - 正常调用 → 更新 score + status
    - 调用失败 → 写 ApiUsageLog error
  run_periodic_refresh:
    - snapshot + fb-data 都执行
    - snapshot 失败不影响 fb-data
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import db as app_db
from app.config import settings
from app.models import ApiUsageLog, Match, MatchOdds, OddsSnapshot
from app.services.periodic_refresh import (
    refresh_match_metadata_from_football_data,
    run_periodic_refresh,
    take_odds_snapshots,
)


def _new_session():
    """动态获取测试 SessionLocal(避免 module-level 缓存失效)."""
    return app_db.SessionLocal()


@pytest.fixture(autouse=True)
def _clean_odds_tables():
    """每个测试前清空 MatchOdds + OddsSnapshot + ApiUsageLog,确保隔离."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).delete()
        db.query(MatchOdds).delete()
        db.query(ApiUsageLog).delete()
        db.commit()
    finally:
        db.close()
    yield


# ============ take_odds_snapshots ============


def test_take_odds_snapshots_adds_for_all_odds():
    """所有 MatchOdds 都追加一条 snapshot."""
    db = _new_session()
    try:
        # 准备:3 条 odds,清掉已有 snapshot
        db.query(OddsSnapshot).delete()
        # 添加测试 odds
        for bm in ["bm1", "bm2", "bm3"]:
            db.add(
                MatchOdds(
                    match_id=1,
                    bookmaker=bm,
                    home_win=2.0,
                    draw=3.0,
                    away_win=4.0,
                    source="manual_test",
                )
            )
        db.commit()
    finally:
        db.close()

    db = _new_session()
    try:
        result = take_odds_snapshots(db)
        assert result["snapshots_added"] == 3
        assert result["snapshots_skipped"] == 0
        assert result["odds_total"] == 3
        # 验证 DB
        snap_count = db.query(OddsSnapshot).count()
        assert snap_count == 3
        # source 都是 periodic_6h
        for s in db.query(OddsSnapshot).all():
            assert s.source == "periodic_6h"
    finally:
        db.close()


def test_take_odds_snapshots_idempotent_within_2s():
    """同一 2s 窗口内重复执行不增加 snapshot(去重)."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).delete()
        db.add(
            MatchOdds(
                match_id=1,
                bookmaker="dup_test",
                home_win=2.0,
                draw=3.0,
                away_win=4.0,
                source="manual_test",
            )
        )
        db.commit()
    finally:
        db.close()

    # 第一次
    db = _new_session()
    try:
        r1 = take_odds_snapshots(db)
        assert r1["snapshots_added"] == 1
        assert r1["snapshots_skipped"] == 0
    finally:
        db.close()

    # 立即第二次(同 2s 窗口)
    db = _new_session()
    try:
        r2 = take_odds_snapshots(db)
        assert r2["snapshots_added"] == 0
        assert r2["snapshots_skipped"] == 1
        # 总数仍是 1
        assert db.query(OddsSnapshot).count() == 1
    finally:
        db.close()


def test_take_odds_snapshots_no_odds_returns_zero():
    """没有 MatchOdds 时返回零,无错误."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).delete()
        db.query(MatchOdds).delete()
        db.commit()
    finally:
        db.close()

    db = _new_session()
    try:
        result = take_odds_snapshots(db)
        assert result["snapshots_added"] == 0
        assert result["odds_total"] == 0
    finally:
        db.close()


# ============ refresh_match_metadata_from_football_data ============


def test_fb_data_skipped_when_disabled():
    """enabled=False → skipped 状态."""
    db = _new_session()
    try:
        original = settings.football_data_enabled
        settings.football_data_enabled = False
        try:
            result = refresh_match_metadata_from_football_data(db)
            assert result["status"] == "skipped"
            assert "enabled" in result["reason"]
        finally:
            settings.football_data_enabled = original
    finally:
        db.close()


def test_fb_data_skipped_when_no_api_key():
    """enabled=True 但无 api_key → skipped."""
    db = _new_session()
    try:
        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = ""
        try:
            result = refresh_match_metadata_from_football_data(db)
            assert result["status"] == "skipped"
            assert "API_KEY" in result["reason"]
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key
    finally:
        db.close()


def test_fb_data_updates_finished_match_score():
    """fb 返回 FINISHED + fullTime → 更新 score + status."""
    db = _new_session()
    try:
        # 重置 match=1 状态,避免被前序测试污染
        m1 = db.query(Match).filter(Match.id == 1).first()
        if m1:
            m1.home_score = None
            m1.away_score = None
            m1.status = "scheduled"
            db.commit()
            db.refresh(m1)

        # mock client
        mock_client = MagicMock()
        mock_client.get_matches_by_date_range.return_value = [
            {
                "homeTeam": {"name": "Mexico"},
                "awayTeam": {"name": "South Africa"},
                "utcDate": "2026-06-12T00:00:00Z",
                "status": "FINISHED",
                "score": {"fullTime": {"home": 2, "away": 1}},
            }
        ]

        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = "test_key"
        try:
            result = refresh_match_metadata_from_football_data(db, client=mock_client)
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key

        assert result["status"] == "ok"
        assert result["matches_updated"] == 1

        # 验证 match=1 已更新
        m1 = db.query(Match).filter(Match.id == 1).first()
        assert m1.home_score == 2
        assert m1.away_score == 1
        assert m1.status == "finished"
    finally:
        db.close()


def test_fb_data_updates_live_status():
    """fb 返回 IN_PLAY → 更新 status=live."""
    db = _new_session()
    try:
        # 重置 match=1
        m1 = db.query(Match).filter(Match.id == 1).first()
        if m1:
            m1.home_score = None
            m1.away_score = None
            m1.status = "scheduled"
            db.commit()

        mock_client = MagicMock()
        mock_client.get_matches_by_date_range.return_value = [
            {
                "homeTeam": {"name": "Mexico"},
                "awayTeam": {"name": "South Africa"},
                "utcDate": "2026-06-12T00:00:00Z",
                "status": "IN_PLAY",
                "score": {},
            }
        ]

        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = "test_key"
        try:
            result = refresh_match_metadata_from_football_data(db, client=mock_client)
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key

        assert result["status"] == "ok"
        m1 = db.query(Match).filter(Match.id == 1).first()
        assert m1.status == "live"
    finally:
        db.close()


def test_fb_data_handles_no_match_found():
    """fb 返回的比赛在本地无对应 → 不报错,只跳过."""
    db = _new_session()
    try:
        mock_client = MagicMock()
        mock_client.get_matches_by_date_range.return_value = [
            {
                "homeTeam": {"name": "Atlantis"},
                "awayTeam": {"name": "Shangrila"},
                "utcDate": "2026-06-12T00:00:00Z",
                "status": "FINISHED",
                "score": {"fullTime": {"home": 5, "away": 0}},
            }
        ]

        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = "test_key"
        try:
            result = refresh_match_metadata_from_football_data(db, client=mock_client)
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key

        assert result["status"] == "ok"
        assert result["matches_updated"] == 0
        assert result["matches_total_in_response"] == 1
    finally:
        db.close()


def test_fb_data_logs_error_on_api_failure():
    """fb API 抛错 → status=error + 写 ApiUsageLog."""
    db = _new_session()
    try:
        # 清理 ApiUsageLog
        db.query(ApiUsageLog).delete()
        db.commit()

        mock_client = MagicMock()
        mock_client.get_matches_by_date_range.side_effect = Exception("API down")

        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = "test_key"
        try:
            result = refresh_match_metadata_from_football_data(db, client=mock_client)
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key

        assert result["status"] == "error"
        assert "API down" in result["error"]

        # 验证 ApiUsageLog
        log = db.query(ApiUsageLog).filter(
            ApiUsageLog.provider == "football_data",
            ApiUsageLog.status == "error",
        ).first()
        assert log is not None
        assert "API down" in log.response_snippet
    finally:
        db.close()


# ============ run_periodic_refresh (编排) ============


def test_run_periodic_refresh_executes_both_steps():
    """snapshot + fb-data 都执行."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).delete()
        db.query(ApiUsageLog).delete()
        db.add(
            MatchOdds(
                match_id=1,
                bookmaker="periodic_test",
                home_win=2.0,
                draw=3.0,
                away_win=4.0,
                source="manual_test",
            )
        )
        db.commit()
    finally:
        db.close()

    mock_client = MagicMock()
    mock_client.get_matches_by_date_range.return_value = []  # 无 fb match

    db = _new_session()
    try:
        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = "test_key"
        try:
            result = run_periodic_refresh(db, fb_client=mock_client)
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key

        assert "executed_at" in result
        assert result["snapshots_added"] >= 1
        assert result["fb_status"] == "ok"
        assert "fb_matches_updated" in result
    finally:
        db.close()


def test_run_periodic_refresh_fb_failure_does_not_block_snapshot():
    """fb-data 失败 → snapshot 仍执行."""
    db = _new_session()
    try:
        db.query(OddsSnapshot).delete()
        db.add(
            MatchOdds(
                match_id=1,
                bookmaker="isolated_test",
                home_win=2.0,
                draw=3.0,
                away_win=4.0,
                source="manual_test",
            )
        )
        db.commit()
    finally:
        db.close()

    mock_client = MagicMock()
    mock_client.get_matches_by_date_range.side_effect = Exception("network fail")

    db = _new_session()
    try:
        original_enabled = settings.football_data_enabled
        original_key = settings.football_data_api_key
        settings.football_data_enabled = True
        settings.football_data_api_key = "test_key"
        try:
            result = run_periodic_refresh(db, fb_client=mock_client)
        finally:
            settings.football_data_enabled = original_enabled
            settings.football_data_api_key = original_key

        # snapshot 仍执行
        assert result["snapshots_added"] >= 1
        # fb-data 失败
        assert result["fb_status"] == "error"
        assert "network fail" in result.get("fb_error", "")
    finally:
        db.close()
