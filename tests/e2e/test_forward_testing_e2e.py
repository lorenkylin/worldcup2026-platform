"""v0.11 Forward-Testing 端到端测试.

测试 Cockpit mini-card 渲染 + 端点.
"""
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8000"
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "screenshots" / "v0.11.0"


def test_live_accuracy_endpoint_exists(page: Page):
    """/api/elo/live-accuracy 端点存在 + 包含必要字段."""
    resp = page.request.get(f"{BASE_URL}/api/elo/live-accuracy")
    assert resp.status == 200, f"端点返回 {resp.status}"
    data = resp.json()
    # v0.11 字段
    assert "is_live_filter" in data
    assert "by_model" in data
    assert "overall" in data
    assert "data_status" in data
    assert "note" in data
    # 无数据场景 (6/17 距开赛 17 天)
    assert data["data_status"] in ("no_data", "live_only", "backfill_only", "mixed")


def test_live_window_accuracy_endpoint(page: Page):
    """/api/elo/live-window-accuracy 默认 7 天窗口."""
    resp = page.request.get(f"{BASE_URL}/api/elo/live-window-accuracy?days=7")
    assert resp.status == 200
    data = resp.json()
    assert data["days"] == 7
    assert "window_start" in data
    assert "window_end" in data
    assert "by_model" in data
    assert "overall" in data


def test_live_accuracy_is_live_filter(page: Page):
    """is_live=true vs false 参数对比."""
    r1 = page.request.get(f"{BASE_URL}/api/elo/live-accuracy?is_live=true").json()
    r2 = page.request.get(f"{BASE_URL}/api/elo/live-accuracy?is_live=false").json()
    r_all = page.request.get(f"{BASE_URL}/api/elo/live-accuracy").json()
    # samples: r_all = r1 + r2 (粗略)
    assert r1["is_live_filter"] is True
    assert r2["is_live_filter"] is False
    assert r_all["is_live_filter"] is None


def test_accuracy_page_renders_live_forward_card(page: Page):
    """/#/accuracy 页面显示真 forward 准确率卡片 (v0.14.2: 从 cockpit 移到准确率页)."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/#/accuracy", wait_until="networkidle")
    time.sleep(2)
    # 准确率页面应包含 live forward 相关文本或模型统计
    body = page.locator("body")
    expect(body).to_contain_text("准确率", timeout=10000)
    page.screenshot(path=str(SCREENSHOTS_DIR / "01-accuracy-live-forward-desktop.png"), full_page=True)


def test_health_includes_current_version(page: Page):
    """/health version 字段为当前版本 (0.14.x)."""
    resp = page.request.get(f"{BASE_URL}/health")
    assert resp.status == 200
    data = resp.json()
    assert data["version"].startswith("0.14")
