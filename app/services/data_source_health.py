"""数据源健康检查服务 (v0.6.0+).

监控 4 个数据源实时可达性:
  1. worldcup26.ir       - 主源 (wc26)
  2. football-data.org   - 增强 (fb-data, 需 token)
  3. StatsBomb Open Data  - 对比源 (GitHub raw, 国内不稳)
  4. worldcupstats.football - 备份 (wcstats)

策略:
  - 实时探测 (调用端点) → 状态 + 延迟
  - 缓存 5min (避免频繁探测)
  - Dashboard 端点一次返回 4 源状态
"""
import time
import httpx
from datetime import datetime, timezone
from typing import Dict, List

from app.config import settings


# 数据源定义
SOURCES = [
    {
        "id": "worldcup26",
        "name": "worldcup26.ir (主源)",
        "url": "https://worldcup26.ir/api/health",
        "type": "primary",
        "description": "104 场赛程/48 队/16 球场/12 组积分榜 - 含已完成赛果",
        "requires_token": False,
    },
    {
        "id": "worldcup26_get",
        "name": "worldcup26.ir /get/* (实际端点)",
        "url": "https://worldcup26.ir/get/teams",
        "type": "primary",
        "description": "真实工作的 API 端点 - 包含已完赛和未开赛数据",
        "requires_token": False,
    },
    {
        "id": "football_data",
        "name": "football-data.org (增强)",
        "url": "https://api.football-data.org/v4/competitions",
        "type": "enhance",
        "description": "赛事元数据增强 (10 req/min 免费层)",
        "requires_token": True,
    },
    {
        "id": "statsbomb",
        "name": "StatsBomb Open Data (对比)",
        "url": "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",
        "type": "compare",
        "description": "大赛级足球数据 - 国内网络常失败",
        "requires_token": False,
    },
    {
        "id": "worldcupstats",
        "name": "worldcupstats.football (备份)",
        "url": "https://worldcupstats.football/",
        "type": "backup",
        "description": "手动同步备份 - 用于 6h 调度窗口外的应急",
        "requires_token": False,
    },
]


def _check_source(source: Dict, timeout: float = 8.0) -> Dict:
    """检查单个数据源."""
    start = time.time()
    try:
        headers = {}
        if source["id"] == "football_data" and settings.football_data_api_key:
            headers["X-Auth-Token"] = settings.football_data_api_key
        with httpx.Client(timeout=timeout) as client:
            r = client.get(source["url"], headers=headers)
            latency_ms = round((time.time() - start) * 1000, 1)
            return {
                "id": source["id"],
                "name": source["name"],
                "type": source["type"],
                "description": source["description"],
                "requires_token": source["requires_token"],
                "url": source["url"],
                "status": "ok" if r.status_code == 200 else "degraded",
                "status_code": r.status_code,
                "latency_ms": latency_ms,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    except httpx.TimeoutException:
        return {
            "id": source["id"], "name": source["name"], "type": source["type"],
            "url": source["url"], "status": "timeout", "status_code": None,
            "latency_ms": round((time.time() - start) * 1000, 1),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": "请求超时 (8s)",
        }
    except Exception as e:
        return {
            "id": source["id"], "name": source["name"], "type": source["type"],
            "url": source["url"], "status": "down", "status_code": None,
            "latency_ms": round((time.time() - start) * 1000, 1),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e)[:200],
        }


def check_all_sources() -> List[Dict]:
    """检查所有数据源 (顺序执行, 避免并行触发风控)."""
    results = [_check_source(s) for s in SOURCES]
    return results


def get_health_summary() -> Dict:
    """健康度汇总 + 总体状态."""
    results = check_all_sources()
    ok = sum(1 for r in results if r["status"] == "ok")
    degraded = sum(1 for r in results if r["status"] in ("degraded", "timeout"))
    down = sum(1 for r in results if r["status"] == "down")
    total = len(results)

    if down == 0 and degraded == 0:
        overall = "all_ok"
    elif down == 0:
        overall = "minor_issue"
    elif ok >= 1:
        overall = "degraded"
    else:
        overall = "critical"

    # 平均延迟
    latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms")]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None

    return {
        "overall": overall,
        "summary": {"total": total, "ok": ok, "degraded": degraded, "down": down},
        "avg_latency_ms": avg_latency,
        "sources": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
