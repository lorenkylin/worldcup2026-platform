"""数据源健康检查 API (v0.6.0+).

GET /api/health/sources - 返回 4 源健康度 + 汇总状态
"""
from fastapi import APIRouter

from app.services.data_source_health import get_health_summary, check_all_sources

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
