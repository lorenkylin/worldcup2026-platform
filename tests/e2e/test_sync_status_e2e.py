"""v0.10 sync_status 端到端测试 (E2E).

覆盖:
1. GET /api/health/sync-status 返回 200 + 完整字段
2. GET /health 增强字段(status/sync_status/db_row_counts/scheduler_running)
3. Cockpit 渲染 📡 数据新鲜度 widget + 颜色编码
"""

import pytest


def test_sync_status_endpoint_returns_complete_payload(page, base_url):
    """GET /api/health/sync-status 返回 200 + 字段完整 (公开, 无 auth)."""
    resp = page.request.get(f"{base_url}/api/health/sync-status")
    assert resp.status == 200, f"sync-status 返回 {resp.status}"

    data = resp.json()
    # 必含字段
    assert "last_success_at" in data
    assert "last_failure_at" in data
    assert "last_error" in data
    assert "consecutive_failures" in data
    assert "total_successes" in data
    assert "total_failures" in data
    # 派生字段
    assert "age_seconds" in data
    assert "freshness" in data
    # freshness 必须在 4 个值之内
    assert data["freshness"] in ("fresh", "stale", "critical", "unknown")


def test_health_endpoint_includes_sync_and_db_rows(page, base_url):
    """GET /health 强化字段: status / sync_status / db_row_counts / scheduler_running."""
    resp = page.request.get(f"{base_url}/health")
    assert resp.status == 200
    data = resp.json()

    # 新增强字段
    assert "status" in data
    assert data["status"] in ("healthy", "degraded", "unhealthy", "unknown")
    assert "sync_status" in data
    assert "db_row_counts" in data
    assert "scheduler_running" in data

    # DB 行数结构
    row_counts = data["db_row_counts"]
    if "error" not in row_counts:
        # 至少应有 matches / teams 字段
        assert "matches" in row_counts
        assert "teams" in row_counts
        assert row_counts["matches"] > 0
        assert row_counts["teams"] > 0


def test_cockpit_renders_freshness_widget(page, base_url):
    """Cockpit 页应渲染 📡 数据新鲜度 widget + 至少一个状态图标."""
    page.goto(f"{base_url}/#/cockpit")
    page.wait_for_load_state("networkidle")
    # 等待渲染 (Cockpit 有多个 await apiWithRetry)
    page.wait_for_timeout(2000)

    # 验证 widget 标题存在
    page.wait_for_selector("text=数据新鲜度", timeout=10000)

    # 验证 4 个字段小标签
    assert page.locator("text=同步状态").count() > 0
    assert page.locator("text=最近成功").count() > 0
    assert page.locator("text=连续失败").count() > 0
    assert page.locator("text=历史成功率").count() > 0

    # 验证阈值说明 (HTML 编码后 < 变 &lt;)
    assert page.locator("text=新鲜").count() > 0
    assert page.locator("text=30 分钟").count() > 0

    # 验证端点标识 (code 标签内的 / 不能用 text=)
    assert page.locator("code", has_text="sync-status").count() > 0

    # 截图 (desktop 默认 1280x720)
    page.screenshot(path="docs/screenshots/v0.10.0/01-cockpit-freshness-desktop.png", full_page=True)

    # 移动端
    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_timeout(500)
    page.screenshot(path="docs/screenshots/v0.10.0/02-cockpit-freshness-mobile.png", full_page=True)