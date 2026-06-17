"""v0.10 同步状态追踪器 — 让主人知道 worldcup26.ir 同步是否健康.

问题:scheduler 是 best-effort, worldcup26.ir 挂了/限流/改了 API 主人都不知道
方案:JSON 文件持久化 + /health 暴露 + stale alarm + Cockpit widget

设计:
- 持久化: data/sync_status.json (避免进程重启丢状态)
- 字段: last_success_at / last_failure_at / last_error / last_result / consecutive_failures
- 调用方: full_sync() 成功/失败后调用 record_success/record_failure
- 读取方: /health 端点 + /api/sync-status + Cockpit
- stale alarm: last_success_at 距今 > 30min 视为 stale, > 60min 视为 critical
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional


_DEFAULT_STATUS = {
    "last_success_at": None,
    "last_failure_at": None,
    "last_error": None,
    "last_result": None,
    "consecutive_failures": 0,
    "total_successes": 0,
    "total_failures": 0,
}


def _status_file_path() -> Path:
    """状态文件路径: data/sync_status.json"""
    return Path(__file__).resolve().parent.parent.parent / "data" / "sync_status.json"


_state_lock = Lock()
_cached_status: Optional[dict] = None


def _load_from_disk() -> dict:
    """从 JSON 文件读状态. 文件不存在返回默认值."""
    path = _status_file_path()
    if not path.exists():
        return dict(_DEFAULT_STATUS)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # 缺失字段兜底
        for k, v in _DEFAULT_STATUS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_STATUS)


def _save_to_disk(status: dict) -> None:
    """原子写 JSON 文件 (tmp + rename 防止半写)."""
    path = _status_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def get_status() -> dict:
    """读当前状态 (含 staleness 派生字段)."""
    global _cached_status
    with _state_lock:
        if _cached_status is None:
            _cached_status = _load_from_disk()
        status = dict(_cached_status)
    # 派生字段: staleness
    now = datetime.now(timezone.utc)
    last_success = status.get("last_success_at")
    if last_success:
        try:
            last_dt = datetime.fromisoformat(last_success)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            age_seconds = (now - last_dt).total_seconds()
            status["age_seconds"] = int(age_seconds)
            if age_seconds < 1800:  # < 30 min
                status["freshness"] = "fresh"
            elif age_seconds < 3600:  # < 60 min
                status["freshness"] = "stale"
            else:
                status["freshness"] = "critical"
        except ValueError:
            status["age_seconds"] = None
            status["freshness"] = "unknown"
    else:
        status["age_seconds"] = None
        status["freshness"] = "unknown"
    return status


def record_success(result: dict) -> None:
    """同步成功时调用."""
    global _cached_status
    with _state_lock:
        if _cached_status is None:
            _cached_status = _load_from_disk()
        _cached_status.update(
            {
                "last_success_at": datetime.now(timezone.utc).isoformat(),
                "last_failure_at": _cached_status.get("last_failure_at"),
                "last_error": None,
                "last_result": result,
                "consecutive_failures": 0,
                "total_successes": _cached_status.get("total_successes", 0) + 1,
            }
        )
        _save_to_disk(_cached_status)


def record_failure(error: str) -> None:
    """同步失败时调用."""
    global _cached_status
    with _state_lock:
        if _cached_status is None:
            _cached_status = _load_from_disk()
        _cached_status.update(
            {
                "last_failure_at": datetime.now(timezone.utc).isoformat(),
                "last_error": error,
                "consecutive_failures": _cached_status.get("consecutive_failures", 0) + 1,
                "total_failures": _cached_status.get("total_failures", 0) + 1,
            }
        )
        _save_to_disk(_cached_status)


def reset() -> None:
    """测试用:清空状态."""
    global _cached_status
    with _state_lock:
        _cached_status = dict(_DEFAULT_STATUS)
        _save_to_disk(_cached_status)