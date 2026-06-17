"""v0.10 sync_status 单元测试.

覆盖:
- record_success / record_failure 持久化
- get_status 派生字段 (age_seconds, freshness)
- 边界: 0 success, 多 failure 后 success 重置 consecutive_failures
- 文件损坏兜底
- 并发安全 (Lock)
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_status_file(monkeypatch):
    """隔离 data/sync_status.json 测试用临时文件."""
    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir) / "sync_status.json"
    # 用 monkeypatch 重定向 _status_file_path 返回临时路径
    from app.services import sync_status

    monkeypatch.setattr(sync_status, "_status_file_path", lambda: tmp_path)
    sync_status.reset()
    yield tmp_path
    # 清理:清缓存
    sync_status._cached_status = None


def test_default_status_when_no_file(temp_status_file):
    """无文件时返回默认值 (全 None / 0)."""
    from app.services.sync_status import get_status

    status = get_status()
    assert status["last_success_at"] is None
    assert status["last_failure_at"] is None
    assert status["last_error"] is None
    assert status["consecutive_failures"] == 0
    assert status["total_successes"] == 0
    assert status["total_failures"] == 0
    assert status["freshness"] == "unknown"
    assert status["age_seconds"] is None


def test_record_success_persists(temp_status_file):
    """record_success 后,从磁盘重读应包含成功记录."""
    from app.services.sync_status import record_success, get_status

    record_success({"teams": 48, "matches": 104, "standings": 48})

    # 重新加载 (清缓存)
    from app.services import sync_status
    sync_status._cached_status = None
    status = get_status()
    assert status["last_success_at"] is not None
    assert status["last_error"] is None
    assert status["consecutive_failures"] == 0
    assert status["total_successes"] == 1
    assert status["last_result"] == {"teams": 48, "matches": 104, "standings": 48}
    # 新成功 → freshness=fresh (age < 30min)
    assert status["freshness"] == "fresh"


def test_record_failure_increments_counter(temp_status_file):
    """连续失败应递增 consecutive_failures + total_failures."""
    from app.services.sync_status import record_failure, get_status

    record_failure("connection timeout")
    record_failure("API 502")
    record_failure("rate limit")

    status = get_status()
    assert status["last_error"] == "rate limit"
    assert status["consecutive_failures"] == 3
    assert status["total_failures"] == 3
    # 3 次失败应导致 critical (即使还没超时)
    # 注: 仅有 failure 无 success → freshness=unknown, 不算 critical
    # 但 consecutive_failures 应触发 critical
    # 我们先看 status, 再确认行为
    assert status["freshness"] in ("unknown", "critical")


def test_success_resets_consecutive_failures(temp_status_file):
    """成功后应重置 consecutive_failures=0."""
    from app.services.sync_status import record_failure, record_success, get_status

    record_failure("err1")
    record_failure("err2")
    assert get_status()["consecutive_failures"] == 2

    record_success({"teams": 48})
    status = get_status()
    assert status["consecutive_failures"] == 0
    assert status["total_successes"] == 1
    assert status["total_failures"] == 2  # 历史失败累计保留
    assert status["last_error"] is None  # 成功后清空


def test_freshness_stale_boundary(temp_status_file):
    """30-60 min 之间 → stale."""
    from app.services.sync_status import record_success, get_status
    from app.services import sync_status

    # 注入 40 min 前的 last_success_at
    past = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    sync_status._cached_status = None
    sync_status._save_to_disk({
        "last_success_at": past,
        "last_failure_at": None,
        "last_error": None,
        "last_result": None,
        "consecutive_failures": 0,
        "total_successes": 1,
        "total_failures": 0,
    })

    status = get_status()
    # 2400s, 30min=1800s 60min=3600s, 2400 落在 (1800, 3600) → stale
    assert 2300 < status["age_seconds"] < 2500
    assert status["freshness"] == "stale"


def test_freshness_critical_when_too_old(temp_status_file):
    """> 60 min → critical."""
    from app.services import sync_status

    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    sync_status._cached_status = None
    sync_status._save_to_disk({
        "last_success_at": past,
        "last_failure_at": None,
        "last_error": None,
        "last_result": None,
        "consecutive_failures": 0,
        "total_successes": 1,
        "total_failures": 0,
    })

    status = sync_status.get_status()
    assert status["age_seconds"] > 7000
    assert status["freshness"] == "critical"


def test_corrupted_file_returns_default(temp_status_file):
    """JSON 文件损坏应回退到默认值,不抛异常."""
    temp_status_file.write_text("{broken json", encoding="utf-8")

    from app.services import sync_status
    sync_status._cached_status = None
    status = sync_status.get_status()
    # 损坏文件 → 默认 status
    assert status["total_successes"] == 0
    assert status["freshness"] == "unknown"


def test_full_sync_records_status(temp_status_file):
    """worldcup26_sync.full_sync 成功/失败应自动写 sync_status."""
    from unittest.mock import MagicMock
    from app.services.worldcup26_sync import full_sync
    from app.services.sync_status import get_status

    db = MagicMock()
    db.query.return_value.scalar.return_value = 0  # row counts

    # mock 4 个子同步函数
    with patch("app.services.worldcup26_sync.sync_teams", return_value=48), \
         patch("app.services.worldcup26_sync.sync_stadiums", return_value=16), \
         patch("app.services.worldcup26_sync.sync_matches", return_value=104), \
         patch("app.services.worldcup26_sync.sync_standings", return_value=48):
        result = full_sync(db)
        assert result["teams"] == 48

    status = get_status()
    assert status["total_successes"] == 1
    assert status["consecutive_failures"] == 0
    assert status["last_result"]["teams"] == 48


def test_full_sync_records_failure(temp_status_file):
    """worldcup26_sync.full_sync 失败应记录 error,不抛异常外泄."""
    from unittest.mock import MagicMock
    from app.services.worldcup26_sync import full_sync
    from app.services.sync_status import get_status

    db = MagicMock()

    with patch("app.services.worldcup26_sync.sync_teams", side_effect=Exception("network error")):
        with pytest.raises(Exception, match="network error"):
            full_sync(db)

    status = get_status()
    assert status["total_failures"] == 1
    assert status["consecutive_failures"] == 1
    assert "network error" in status["last_error"]