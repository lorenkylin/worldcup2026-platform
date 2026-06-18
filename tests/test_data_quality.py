"""数据质量校验工具测试（v0.14.1）."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import data_quality
from app.services.data_quality import DataQualityError


class TestParseIsoTimestamp:
    def test_parse_string_with_z(self):
        dt = data_quality.parse_iso_timestamp("2026-06-12T12:00:00Z")
        assert dt == datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)

    def test_parse_naive_datetime(self):
        dt = data_quality.parse_iso_timestamp(datetime(2026, 6, 12, 12, 0, 0))
        assert dt == datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)

    def test_parse_invalid_returns_none(self):
        assert data_quality.parse_iso_timestamp("not-a-date") is None


class TestFreshness:
    def test_fresh_within_window(self):
        now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
        recorded = now - timedelta(minutes=5)
        assert data_quality.is_fresh(recorded, max_age_seconds=600, now=now) is True

    def test_stale_outside_window(self):
        now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
        recorded = now - timedelta(hours=2)
        assert data_quality.is_fresh(recorded, max_age_seconds=3600, now=now) is False

    def test_future_data_rejected(self):
        now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
        recorded = now + timedelta(minutes=2)
        assert data_quality.is_fresh(recorded, max_age_seconds=600, now=now) is False

    def test_missing_timestamp_treated_as_fresh(self):
        assert data_quality.is_fresh(None, max_age_seconds=600) is True


class TestDeduplicate:
    def test_keep_last(self):
        items = [{"id": "a", "v": 1}, {"id": "a", "v": 2}, {"id": "b", "v": 3}]
        result = data_quality.deduplicate(items, key_func=lambda x: x["id"], keep="last")
        assert result == [{"id": "a", "v": 2}, {"id": "b", "v": 3}]

    def test_keep_first(self):
        items = [{"id": "a", "v": 1}, {"id": "a", "v": 2}, {"id": "b", "v": 3}]
        result = data_quality.deduplicate(items, key_func=lambda x: x["id"], keep="first")
        assert result == [{"id": "a", "v": 1}, {"id": "b", "v": 3}]

    def test_skip_none_key(self):
        items = [{"id": None, "v": 1}, {"id": "a", "v": 2}]
        result = data_quality.deduplicate(items, key_func=lambda x: x["id"])
        assert result == [{"id": "a", "v": 2}]


class TestAssertUnique:
    def test_warning_on_duplicates(self):
        items = [{"id": "a"}, {"id": "a"}]
        dups = data_quality.assert_unique(
            items, key_func=lambda x: x["id"], label="test-items", raise_on_dup=False
        )
        assert dups == ["a"]

    def test_raise_on_duplicates(self):
        items = [{"id": "a"}, {"id": "a"}]
        with pytest.raises(DataQualityError):
            data_quality.assert_unique(
                items, key_func=lambda x: x["id"], label="test-items", raise_on_dup=True
            )


class TestStatusTransition:
    def test_scheduled_to_live_allowed(self):
        assert data_quality.is_status_transition_allowed("scheduled", "live") is True

    def test_live_to_finished_allowed(self):
        assert data_quality.is_status_transition_allowed("live", "finished") is True

    def test_finished_to_scheduled_blocked(self):
        assert data_quality.is_status_transition_allowed("finished", "scheduled") is False

    def test_same_status_allowed(self):
        assert data_quality.is_status_transition_allowed("live", "live") is True


class TestSourcePriority:
    def test_api_football_can_overwrite_worldcup26(self):
        assert data_quality.can_overwrite("worldcup26.ir", "api-football") is True

    def test_worldcup26_cannot_overwrite_fresh_api_football(self):
        updated_at = data_quality.now_utc() - timedelta(hours=1)
        assert data_quality.can_overwrite("api-football", "worldcup26.ir", updated_at) is False

    def test_worldcup26_cannot_overwrite_stale_api_football(self):
        # v0.14.3: 低优先级源不再因过期而覆盖高优先级静态数据
        updated_at = data_quality.now_utc() - timedelta(hours=7)
        assert data_quality.can_overwrite("api-football", "worldcup26.ir", updated_at) is False

    def test_manual_cannot_be_overwritten(self):
        assert data_quality.can_overwrite("manual", "api-football") is False
        assert data_quality.can_overwrite("manual", "worldcup26.ir") is False

    def test_fixtures_cannot_be_overwritten_by_worldcup26(self):
        assert data_quality.can_overwrite("fixtures", "worldcup26.ir") is False

    def test_api_football_can_overwrite_fixtures(self):
        # api-football 与 fixtures 同优先级 2，允许覆盖取最新
        assert data_quality.can_overwrite("fixtures", "api-football") is True

    def test_same_source_can_overwrite(self):
        assert data_quality.can_overwrite("api-football", "api-football") is True


class TestSeasonWindow:
    def test_kickoff_inside_window(self):
        dt = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert data_quality.is_within_season_window(dt) is True

    def test_kickoff_outside_window(self):
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert data_quality.is_within_season_window(dt) is False


class TestSourceQualitySummary:
    def test_summary_flags_duplicates(self):
        items = [{"id": "a"}, {"id": "a"}, {"id": "b"}]
        summary = data_quality.source_quality_summary(items, key_func=lambda x: x["id"])
        assert summary["total"] == 3
        assert summary["duplicates"] == 1
        assert summary["duplicate_keys"] == ["a"]
        assert summary["quality_ok"] is False

    def test_summary_ok_when_unique(self):
        items = [{"id": "a"}, {"id": "b"}]
        summary = data_quality.source_quality_summary(items, key_func=lambda x: x["id"])
        assert summary["quality_ok"] is True
