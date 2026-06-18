"""API-Football 预算告警服务 (v0.14.3).

职责:
  1. 跟踪 API-Football 日调用量使用率。
  2. 当使用率达到阈值时触发告警（邮件 SMTP / 企业微信 webhook）。
  3. 防止重复告警：按 UTC 日期 + 告警级别记录，每天每个级别只告警一次。
  4. 暴露当前预算状态供 /api/health/sources 使用。

无外部通知渠道配置时，仅记录状态与日志，不抛异常。
"""

from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AlertLevel:
    """告警级别."""

    OK = "ok"
    WARNING = "warning"  # 例如 >= 80%
    CRITICAL = "critical"  # 例如 >= 95% 或已用尽


class BudgetAlertManager:
    """API-Football 日预算告警管理器."""

    DEFAULT_THRESHOLD_WARNING = 0.80
    DEFAULT_THRESHOLD_CRITICAL = 0.95

    def __init__(
        self,
        status_path: Optional[Path] = None,
        threshold_warning: Optional[float] = None,
        threshold_critical: Optional[float] = None,
    ) -> None:
        self._status_path = status_path or self._default_status_path()
        self.threshold_warning = threshold_warning or getattr(
            settings, "api_football_budget_warning_threshold", self.DEFAULT_THRESHOLD_WARNING
        )
        self.threshold_critical = threshold_critical or getattr(
            settings, "api_football_budget_critical_threshold", self.DEFAULT_THRESHOLD_CRITICAL
        )
        self._lock = Lock()
        self._status: Optional[Dict] = None

    @staticmethod
    def _default_status_path() -> Path:
        """默认状态文件路径，跟随 DATA_DIR."""
        data_dir = Path(getattr(settings, "data_dir", "./data"))
        return data_dir / "budget_alert_status.json"

    def _load_status(self) -> Dict:
        """加载持久化状态."""
        if self._status is not None:
            return self._status
        if self._status_path.exists():
            try:
                with self._status_path.open("r", encoding="utf-8") as f:
                    self._status = json.load(f)
                return self._status
            except Exception as exc:  # noqa: BLE001
                logger.warning("[budget_alert] 加载状态文件失败: %s", exc)
        self._status = {
            "last_alert_level": AlertLevel.OK,
            "last_alert_at": None,
            "last_alert_date": None,
            "alerts_total": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._status

    def _save_status(self, status: Dict) -> None:
        """持久化状态."""
        status["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._status_path.parent.mkdir(parents=True, exist_ok=True)
            # 原子写入避免并发损坏
            tmp_path = self._status_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
            tmp_path.replace(self._status_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[budget_alert] 保存状态文件失败: %s", exc)

    def _current_level(self, usage_ratio: float) -> str:
        """根据使用率判断告警级别."""
        if usage_ratio >= self.threshold_critical:
            return AlertLevel.CRITICAL
        if usage_ratio >= self.threshold_warning:
            return AlertLevel.WARNING
        return AlertLevel.OK

    def _should_alert(self, level: str) -> bool:
        """判断是否应该触发告警（跨级别才告警，同一天同一级别只告警一次）."""
        status = self._load_status()
        today = datetime.now(timezone.utc).date().isoformat()
        last_level = status.get("last_alert_level", AlertLevel.OK)
        last_date = status.get("last_alert_date")

        # 级别没有变化且是同一天，不重复告警
        if level == last_level and today == last_date:
            return False
        # OK 状态不需要告警
        if level == AlertLevel.OK:
            return False
        return True

    def _send_email(self, subject: str, body: str) -> bool:
        """发送邮件告警."""
        smtp_host = getattr(settings, "alert_email_smtp_host", "")
        smtp_port = getattr(settings, "alert_email_smtp_port", 587)
        smtp_user = getattr(settings, "alert_email_smtp_user", "")
        smtp_password = getattr(settings, "alert_email_smtp_password", "")
        from_addr = getattr(settings, "alert_email_from", "")
        to_addrs = getattr(settings, "alert_email_to", "")

        if not all([smtp_host, smtp_user, from_addr, to_addrs]):
            logger.info("[budget_alert] 邮件告警未配置，跳过发送")
            return False

        if isinstance(to_addrs, str):
            to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[budget_alert] 邮件发送失败: %s", exc)
            return False

    def _send_wechat(self, message: str) -> bool:
        """发送企业微信 webhook 告警."""
        webhook_url = getattr(settings, "alert_wechat_webhook_url", "")
        if not webhook_url:
            logger.info("[budget_alert] 企业微信告警未配置，跳过发送")
            return False

        payload = {"msgtype": "text", "text": {"content": message}}
        try:
            with httpx.Client(timeout=10) as client:
                r = client.post(webhook_url, json=payload)
                r.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[budget_alert] 企业微信发送失败: %s", exc)
            return False

    def _dispatch_alert(self, level: str, used: int, limit: int, ratio: float) -> Dict:
        """分发告警到已配置的渠道."""
        emoji = {"warning": "⚠️", "critical": "🚨"}.get(level, "")
        subject = f"{emoji} 2026 世界杯平台 API-Football 预算告警 [{level.upper()}]"
        body = (
            f"告警级别: {level.upper()}\n"
            f"已用配额: {used} / {limit} ({ratio:.1%})\n"
            f"阈值: warning={self.threshold_warning:.0%}, critical={self.threshold_critical:.0%}\n"
            f"时间: {datetime.now(timezone.utc).isoformat()}\n"
            f"建议: 检查调度器频率或升级 API-Football 套餐。"
        )

        email_ok = self._send_email(subject, body)
        wechat_ok = self._send_wechat(body)

        return {
            "email_sent": email_ok,
            "wechat_sent": wechat_ok,
            "channels_configured": bool(
                getattr(settings, "alert_email_smtp_host", "")
                or getattr(settings, "alert_wechat_webhook_url", "")
            ),
        }

    def check_and_alert(self, used: int, limit: int) -> Dict:
        """检查预算并触发告警.

        Args:
            used: 当日已用请求数。
            limit: 当日配额上限。

        Returns:
            当前预算状态字典。
        """
        with self._lock:
            ratio = used / limit if limit > 0 else 0.0
            level = self._current_level(ratio)
            status = self._load_status()

            alert_result = {"triggered": False, "details": None}
            if self._should_alert(level):
                alert_result["triggered"] = True
                alert_result["details"] = self._dispatch_alert(level, used, limit, ratio)

                status["last_alert_level"] = level
                status["last_alert_at"] = datetime.now(timezone.utc).isoformat()
                status["last_alert_date"] = datetime.now(timezone.utc).date().isoformat()
                status["alerts_total"] = status.get("alerts_total", 0) + 1
                self._save_status(status)

            # 当级别从 critical/warning 回到 ok 时，也更新状态（不告警）
            if level == AlertLevel.OK and status.get("last_alert_level") != AlertLevel.OK:
                status["last_alert_level"] = AlertLevel.OK
                status["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_status(status)

            return {
                "enabled": limit > 0,
                "daily_limit": limit,
                "used_today": used,
                "remaining": max(0, limit - used),
                "usage_ratio": round(ratio, 4),
                "level": level,
                "threshold_warning": self.threshold_warning,
                "threshold_critical": self.threshold_critical,
                "last_alert": {
                    "level": status.get("last_alert_level"),
                    "at": status.get("last_alert_at"),
                },
                "alert_triggered": alert_result["triggered"],
            }

    def get_status(self, used: int = 0, limit: int = 0) -> Dict:
        """获取当前预算状态（不触发告警）."""
        ratio = used / limit if limit > 0 else 0.0
        level = self._current_level(ratio)
        status = self._load_status()
        return {
            "enabled": limit > 0,
            "daily_limit": limit,
            "used_today": used,
            "remaining": max(0, limit - used),
            "usage_ratio": round(ratio, 4),
            "level": level,
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "last_alert": {
                "level": status.get("last_alert_level"),
                "at": status.get("last_alert_at"),
            },
        }


# 模块级单例，避免多个 client 实例创建多个 manager
_alert_manager: Optional[BudgetAlertManager] = None
_manager_lock = Lock()


def get_budget_alert_manager() -> BudgetAlertManager:
    """获取预算告警管理器单例."""
    global _alert_manager
    if _alert_manager is None:
        with _manager_lock:
            if _alert_manager is None:
                _alert_manager = BudgetAlertManager()
    return _alert_manager
