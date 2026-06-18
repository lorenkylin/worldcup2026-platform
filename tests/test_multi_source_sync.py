"""多源同步编排器测试（v0.14.0）.

验证：
- API-Football 成功时优先使用
- API-Football 失败/未启用时回退 worldcup26.ir
- 手动录入的数据不被覆盖
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

from app import config as config_module
from app.models import Match
from app.services import api_football_sync, multi_source_sync
from app.services.api_football import ApiFootballClient


def _fixture_response_mex_rsa():
    """构造 API-Football fixture 响应（对应 conftest 种子比赛）."""
    return [
        {
            "fixture": {
                "id": 12345,
                "date": "2026-06-12T00:00:00+00:00",
                "status": {"short": "FT"},
            },
            "teams": {
                "home": {"name": "Mexico", "code": "MEX"},
                "away": {"name": "South Africa", "code": "RSA"},
            },
            "goals": {"home": 2, "away": 1},
            "score": {"fulltime": {"home": 2, "away": 1}},
            "league": {"round": "Group A - 1"},
        }
    ]


class TestMultiSourceFullSync:
    def test_api_football_primary_when_enabled(self, db_session):
        """API-Football 启用且成功时，优先使用它."""
        with patch.object(config_module.settings, "api_football_enabled", True), \
             patch.object(config_module.settings, "api_football_key", "test_key"), \
             patch("app.services.multi_source_sync._post_sync_hook", return_value={"coords": 0, "form": 0}), \
             patch("app.services.multi_source_sync.sync_status.record_success") as mock_record:

            api_summary = {
                "source": "api-football",
                "teams": {"updated": 0, "skipped": 48},
                "fixtures": {
                    "updated": 10,
                    "skipped": 0,
                    "not_found": 0,
                    "quality": {"total": 10, "duplicates": 0, "fresh": 10, "stale": 0, "quality_ok": True},
                },
                "standings": {"updated": 48, "skipped": 0},
                "events": {"updated": 5, "skipped": 0},
            }
            with patch.object(api_football_sync, "sync_all", return_value=api_summary):
                result = multi_source_sync.full_sync(db_session)

            assert result["ok"] is True
            assert result["primary_source"] == "api-football"
            assert result["api_football"] == api_summary
            mock_record.assert_called_once()

    def test_fallback_to_worldcup26_when_disabled(self, db_session):
        """未启用 API-Football 时回退 worldcup26.ir."""
        with patch.object(config_module.settings, "api_football_enabled", False), \
             patch.object(config_module.settings, "api_football_key", ""), \
             patch("app.services.multi_source_sync._post_sync_hook", return_value={"coords": 0, "form": 0}), \
             patch("app.services.multi_source_sync.sync_status.record_success") as mock_record, \
             patch("app.services.worldcup26_sync.full_sync") as mock_wc26:

            mock_wc26.return_value = {
                "teams": 48, "stadiums": 16, "matches": 104, "standings": 48
            }
            result = multi_source_sync.full_sync(db_session)

            assert result["ok"] is True
            assert result["primary_source"] == "worldcup26.ir"
            mock_wc26.assert_called_once()
            mock_record.assert_called_once()

    def test_fallback_when_api_football_fails(self, db_session):
        """API-Football 抛出异常时回退 worldcup26.ir."""
        with patch.object(config_module.settings, "api_football_enabled", True), \
             patch.object(config_module.settings, "api_football_key", "test_key"), \
             patch("app.services.multi_source_sync._post_sync_hook", return_value={"coords": 0, "form": 0}), \
             patch("app.services.worldcup26_sync.full_sync") as mock_wc26, \
             patch("app.services.multi_source_sync.sync_status.record_success") as mock_record:

            with patch.object(api_football_sync, "sync_all", side_effect=Exception("API quota exhausted")):
                mock_wc26.return_value = {"teams": 48, "stadiums": 16, "matches": 104, "standings": 48}
                result = multi_source_sync.full_sync(db_session)

            assert result["ok"] is True
            assert result["primary_source"] == "worldcup26.ir"
            assert "API quota exhausted" in result["api_football_error"]
            mock_wc26.assert_called_once()
            mock_record.assert_called_once()


class TestMultiSourceLiveSync:
    def test_api_football_live_when_match_in_window(self, db_session):
        """未来 3h 内有比赛且启用 API-Football 时，使用 API-Football."""
        match = db_session.query(Match).filter(Match.id == 1).first()
        match.kickoff_at = datetime.now(timezone.utc) + timedelta(hours=1)
        match.data_source = "api-football"
        db_session.commit()

        with patch.object(config_module.settings, "api_football_enabled", True), \
             patch.object(config_module.settings, "api_football_key", "test_key"), \
             patch("app.services.multi_source_sync.sync_status.record_success") as mock_record:

            with patch.object(api_football_sync, "sync_fixtures", return_value={
                "updated": 1,
                "skipped": 0,
                "not_found": 0,
                "source": "api-football",
                "quality": {"total": 1, "duplicates": 0, "fresh": 1, "stale": 0, "quality_ok": True},
            }) as mock_sync:
                result = multi_source_sync.live_sync(db_session)

            assert result["ok"] is True
            assert result["primary_source"] == "api-football"
            mock_sync.assert_called_once()
            mock_record.assert_called_once()

    def test_live_fallback_to_worldcup26_when_no_key(self, db_session):
        """未启用 API-Football 时，live_sync 回退 worldcup26.ir."""
        with patch.object(config_module.settings, "api_football_enabled", False), \
             patch("app.services.worldcup26_sync.full_sync") as mock_wc26, \
             patch("app.services.multi_source_sync.sync_status.record_success") as mock_record:

            mock_wc26.return_value = {"teams": 48, "stadiums": 16, "matches": 104, "standings": 48}
            result = multi_source_sync.live_sync(db_session)

            assert result["ok"] is True
            assert result["primary_source"] == "worldcup26.ir"
            mock_wc26.assert_called_once()
            mock_record.assert_called_once()


class TestManualSourceProtection:
    def test_manual_match_not_overwritten_by_api_football(self, db_session):
        """data_source=='manual' 时，API-Football 不覆盖比分/状态."""
        match = db_session.query(Match).filter(Match.id == 1).first()
        assert match.data_source == "manual"

        def handler(request: httpx.Request):
            return httpx.Response(
                200,
                json={"response": _fixture_response_mex_rsa(), "errors": []},
            )

        client = ApiFootballClient(
            api_key="test", _transport=httpx.MockTransport(handler)
        )

        with patch.object(config_module.settings, "api_football_league_id", 1), \
             patch.object(config_module.settings, "api_football_season", 2026):
            result = api_football_sync.sync_fixtures(db_session, client=client)

        assert result["updated"] == 0  # 手动数据源优先级更高，API-Football 跳过
        db_session.refresh(match)
        assert match.status == "scheduled"  # 手动数据不被覆盖
        assert match.home_score is None
        assert match.away_score is None
        assert match.data_source == "manual"
