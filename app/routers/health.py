"""数据源健康检查 API (v0.6.0+).

GET /api/health/sources - 返回 4 源健康度 + 汇总状态
GET /api/health/sync-status - v0.10 数据新鲜度 (公开,无 admin 鉴权)
"""
from fastapi import APIRouter

from app.services.data_source_health import get_health_summary, check_all_sources
from app.services.sync_status import get_status

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/sources")
def sources_health():
    """数据源健康度 dashboard.

    Returns:
        {
            "overall": "all_ok" | "minor_issue" | "degraded" | "critical",
            "summary": {total, ok, degraded, down},
            "avg_latency_ms": float,
            "sources": [{id, name, status, latency_ms, ...}],
            "checked_at": ISO timestamp
        }
    """
    return get_health_summary()


@router.get("/sources/{source_id}")
def source_detail(source_id: str):
    """单个数据源详情 (e.g. worldcup26)."""
    from app.services.data_source_health import SOURCES, _check_source
    for s in SOURCES:
        if s["id"] == source_id:
            return _check_source(s)
    return {"error": f"未知数据源: {source_id}"}


@router.get("/sync-status")
def sync_status_endpoint():
    """v0.10 数据同步状态 (公开, Cockpit widget 用).

    Returns:
        {
            "last_success_at": ISO timestamp or None,
            "last_failure_at": ISO timestamp or None,
            "last_error": str or None,
            "last_result": {teams, stadiums, matches, standings, synced_at} or None,
            "consecutive_failures": int,
            "total_successes": int,
            "total_failures": int,
            "age_seconds": int or None (距 last_success 多少秒),
            "freshness": "fresh" | "stale" | "critical" | "unknown"
        }

    阈值:
    - fresh: age < 30 min
    - stale: 30 min <= age < 60 min
    - critical: age >= 60 min 或连续失败 >= 3 次
    """
    return get_status()
