"""数据源健康检查单测 (v0.14.0+)."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import httpx

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from app.services.data_source_health import (
    SOURCES, _check_source, _check_api_football_health, get_health_summary, check_all_sources,
)


def _source_by_id(source_id: str):
    """按 id 取数据源定义."""
    return next(s for s in SOURCES if s["id"] == source_id)


class TestCheckSource:
    def test_ok_status(self):
        """Mock 200 返回 ok."""
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            with patch("app.services.data_source_health.settings") as mock_settings:
                mock_settings.football_data_api_key = ""
                result = _check_source(_source_by_id("worldcup26"))
            assert result["status"] == "ok"
            assert result["status_code"] == 200
            assert "latency_ms" in result

    def test_degraded_status(self):
        """Mock 4xx 返回 degraded."""
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            with patch("app.services.data_source_health.settings") as mock_settings:
                mock_settings.football_data_api_key = ""
                result = _check_source(_source_by_id("worldcup26"))
            assert result["status"] == "degraded"
            assert result["status_code"] == 404

    def test_timeout(self):
        """Mock 超时."""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.TimeoutException("slow")
            with patch("app.services.data_source_health.settings") as mock_settings:
                mock_settings.football_data_api_key = ""
                result = _check_source(_source_by_id("worldcup26"))
            assert result["status"] == "timeout"

    def test_down_status(self):
        """Mock DNS 错误."""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("DNS failed")
            with patch("app.services.data_source_health.settings") as mock_settings:
                mock_settings.football_data_api_key = ""
                result = _check_source(_source_by_id("worldcup26"))
            assert result["status"] == "down"
            assert "error" in result

    def test_football_data_uses_token(self):
        """football-data.org 源应自动加 X-Auth-Token header (如果有 token)."""
        with patch("httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            with patch("app.services.data_source_health.settings") as mock_settings:
                mock_settings.football_data_api_key = "test_token_123"
                _check_source(_source_by_id("football_data"))
                # 验证 X-Auth-Token header 注入
                call_args = mock_client.return_value.__enter__.return_value.get.call_args
                assert call_args is not None
                headers = call_args.kwargs.get("headers", {})
                assert headers.get("X-Auth-Token") == "test_token_123"


class TestApiFootballHealth:
    def test_disabled_when_no_key(self):
        """未启用时返回 disabled."""
        with patch("app.services.data_source_health.settings") as mock_settings:
            mock_settings.api_football_enabled = False
            mock_settings.api_football_key = ""
            result = _check_api_football_health(_source_by_id("api_football"))
            assert result["status"] == "disabled"

    def test_ok_when_recent_success(self):
        """30min 内有成功同步则 ok."""
        now = "2026-06-17T12:00:00+00:00"
        with patch("app.services.data_source_health.settings") as mock_settings:
            mock_settings.api_football_enabled = True
            mock_settings.api_football_key = "test"
            with patch("app.services.data_source_health.sync_status.get_status") as mock_get:
                mock_get.return_value = {
                    "last_success_at": now,
                    "consecutive_failures": 0,
                }
                with patch("app.services.data_source_health.datetime") as mock_dt:
                    mock_dt.now.return_value = MagicMock(
                        isoformat=lambda: now,
                        __sub__=lambda self, other: MagicMock(total_seconds=lambda: 60),
                    )
                    mock_dt.fromisoformat = datetime.fromisoformat
                    mock_dt.timezone = timezone
                    result = _check_api_football_health(_source_by_id("api_football"))
                    assert result["status"] == "ok"

    def test_down_after_many_failures(self):
        """连续失败 3 次返回 down."""
        with patch("app.services.data_source_health.settings") as mock_settings:
            mock_settings.api_football_enabled = True
            mock_settings.api_football_key = "test"
            with patch("app.services.data_source_health.sync_status.get_status") as mock_get:
                mock_get.return_value = {
                    "last_success_at": "2026-06-17T10:00:00+00:00",
                    "consecutive_failures": 3,
                }
                result = _check_api_football_health(_source_by_id("api_football"))
                assert result["status"] == "down"


class TestHealthSummary:
    def test_summary_format(self):
        """汇总格式正确."""
        with patch("app.services.data_source_health.check_all_sources") as mock_check:
            mock_check.return_value = [
                {"id": "s1", "name": "S1", "type": "primary", "url": "u1",
                 "status": "ok", "status_code": 200, "latency_ms": 100,
                 "checked_at": "2026-01-01"},
                {"id": "s2", "name": "S2", "type": "backup", "url": "u2",
                 "status": "down", "status_code": None, "latency_ms": 50,
                 "checked_at": "2026-01-01", "error": "DNS"},
            ]
            summary = get_health_summary()
            assert summary["overall"] == "degraded"  # 1 ok + 1 down
            assert summary["summary"] == {"total": 2, "ok": 1, "degraded": 0, "down": 1}
            assert summary["avg_latency_ms"] == 75.0
            assert len(summary["sources"]) == 2

    def test_overall_all_ok(self):
        with patch("app.services.data_source_health.check_all_sources") as mock_check:
            mock_check.return_value = [
                {"id": "s1", "name": "S1", "type": "primary", "url": "u1",
                 "status": "ok", "status_code": 200, "latency_ms": 100, "checked_at": "t"},
            ]
            summary = get_health_summary()
            assert summary["overall"] == "all_ok"

    def test_overall_critical(self):
        with patch("app.services.data_source_health.check_all_sources") as mock_check:
            mock_check.return_value = [
                {"id": "s1", "name": "S1", "type": "primary", "url": "u1",
                 "status": "down", "status_code": None, "latency_ms": 50, "checked_at": "t", "error": "x"},
            ]
            summary = get_health_summary()
            assert summary["overall"] == "critical"


class TestSourcesList:
    def test_all_6_sources_defined(self):
        """6 个数据源: api-football + wc26(2)+fb-data+statsbomb+wcstats."""
        assert len(SOURCES) == 6
        ids = {s["id"] for s in SOURCES}
        assert "api_football" in ids
        assert "worldcup26" in ids
        assert "worldcup26_get" in ids
        assert "football_data" in ids
        assert "statsbomb" in ids
        assert "worldcupstats" in ids
