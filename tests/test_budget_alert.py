"""API-Football 预算告警测试 (v0.14.3)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.budget_alert import AlertLevel, BudgetAlertManager


@pytest.fixture
def tmp_manager(tmp_path):
    """提供使用临时状态文件的 BudgetAlertManager."""
    status_path = tmp_path / "budget_alert_status.json"
    return BudgetAlertManager(
        status_path=status_path,
        threshold_warning=0.80,
        threshold_critical=0.95,
    )


class TestBudgetAlertLevels:
    """告警级别判定."""

    def test_ok_level(self, tmp_manager):
        assert tmp_manager._current_level(0.0) == AlertLevel.OK
        assert tmp_manager._current_level(0.79) == AlertLevel.OK

    def test_warning_level(self, tmp_manager):
        assert tmp_manager._current_level(0.80) == AlertLevel.WARNING
        assert tmp_manager._current_level(0.94) == AlertLevel.WARNING

    def test_critical_level(self, tmp_manager):
        assert tmp_manager._current_level(0.95) == AlertLevel.CRITICAL
        assert tmp_manager._current_level(1.00) == AlertLevel.CRITICAL


class TestBudgetAlertStatus:
    """状态持久化."""

    def test_load_default_status(self, tmp_manager):
        status = tmp_manager._load_status()
        assert status["last_alert_level"] == AlertLevel.OK
        assert status["alerts_total"] == 0

    def test_save_and_load_status(self, tmp_manager):
        status = tmp_manager._load_status()
        status["last_alert_level"] = AlertLevel.WARNING
        tmp_manager._save_status(status)

        # 重新实例化，验证持久化
        manager2 = BudgetAlertManager(
            status_path=tmp_manager._status_path,
            threshold_warning=0.80,
            threshold_critical=0.95,
        )
        loaded = manager2._load_status()
        assert loaded["last_alert_level"] == AlertLevel.WARNING


class TestBudgetAlertDeduplication:
    """告警去重."""

    def test_same_level_same_day_not_duplicate(self, tmp_manager):
        # 第一次 warning 触发
        result1 = tmp_manager.check_and_alert(80, 100)
        assert result1["alert_triggered"] is True

        # 同一天同级别不重复触发
        result2 = tmp_manager.check_and_alert(81, 100)
        assert result2["alert_triggered"] is False

    def test_ok_resets_and_can_retrigger(self, tmp_manager):
        # 触发 warning
        tmp_manager.check_and_alert(80, 100)

        # 回到 OK
        result_ok = tmp_manager.check_and_alert(10, 100)
        assert result_ok["level"] == AlertLevel.OK

        # 再次 warning 应该触发
        result2 = tmp_manager.check_and_alert(85, 100)
        assert result2["alert_triggered"] is True


class TestBudgetAlertDispatch:
    """告警分发."""

    def test_no_channels_configured_logs_only(self, tmp_manager):
        with patch("app.services.budget_alert.settings") as mock_settings:
            mock_settings.alert_email_smtp_host = ""
            mock_settings.alert_wechat_webhook_url = ""
            result = tmp_manager.check_and_alert(95, 100)
            assert result["alert_triggered"] is True
            assert result["level"] == AlertLevel.CRITICAL

    def test_email_channel_called(self, tmp_manager):
        with patch("app.services.budget_alert.settings") as mock_settings, \
             patch("smtplib.SMTP") as mock_smtp:
            mock_settings.alert_email_smtp_host = "smtp.example.com"
            mock_settings.alert_email_smtp_port = 587
            mock_settings.alert_email_smtp_user = "user@example.com"
            mock_settings.alert_email_smtp_password = "secret"
            mock_settings.alert_email_from = "from@example.com"
            mock_settings.alert_wechat_webhook_url = ""

            result = tmp_manager.check_and_alert(95, 100)
            assert result["alert_triggered"] is True
            mock_smtp.assert_called_once()

    def test_wechat_channel_called(self, tmp_manager):
        with patch("app.services.budget_alert.settings") as mock_settings, \
             patch("httpx.Client") as mock_client:
            mock_settings.alert_email_smtp_host = ""
            mock_settings.alert_wechat_webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"

            result = tmp_manager.check_and_alert(95, 100)
            assert result["alert_triggered"] is True
            mock_client.return_value.__enter__.return_value.post.assert_called_once()


class TestBudgetAlertStatusExposure:
    """状态暴露."""

    def test_get_status_no_alert(self, tmp_manager):
        status = tmp_manager.get_status(used=50, limit=100)
        assert status["enabled"] is True
        assert status["daily_limit"] == 100
        assert status["used_today"] == 50
        assert status["remaining"] == 50
        assert status["usage_ratio"] == 0.5
        assert status["level"] == AlertLevel.OK

    def test_get_status_critical(self, tmp_manager):
        status = tmp_manager.get_status(used=99, limit=100)
        assert status["level"] == AlertLevel.CRITICAL
        assert status["remaining"] == 1


class TestBudgetAlertFileAtomicWrite:
    """状态文件原子写入."""

    def test_atomic_write(self, tmp_manager):
        tmp_manager.check_and_alert(80, 100)
        assert tmp_manager._status_path.exists()
        # 验证 JSON 可解析
        data = json.loads(tmp_manager._status_path.read_text(encoding="utf-8"))
        assert data["last_alert_level"] == AlertLevel.WARNING
        assert data["alerts_total"] == 1
