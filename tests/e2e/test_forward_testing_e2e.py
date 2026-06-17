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


def test_cockpit_live_accuracy_card_desktop(page: Page):
    """Cockpit 显示真 forward 准确率 mini-card (桌面 1440x900)."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/#/cockpit", wait_until="networkidle")
    time.sleep(2)
    # 标题存在 (用 h2 + 文本)
    card_title = page.locator("h2", has_text="真 Forward 准确率")
    expect(card_title.first).to_be_visible(timeout=10000)
    # 截图
    page.screenshot(path=str(SCREENSHOTS_DIR / "01-cockpit-live-forward-desktop.png"), full_page=True)
    # 验证 mini-card 3 列 (整体 / Brier / 状态)
    card = page.locator("section", has=card_title.first).first
    cards_3 = card.locator(".grid > div")
    assert cards_3.count() == 3, f"应为 3 张 mini-card, 实际 {cards_3.count()}"


def test_cockpit_live_accuracy_card_mobile(page: Page):
    """Cockpit 真 forward 准确率 mini-card 移动端 375x812."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{BASE_URL}/#/cockpit", wait_until="networkidle")
    time.sleep(2)
    card_title = page.locator("h2", has_text="真 Forward 准确率")
    expect(card_title.first).to_be_visible(timeout=10000)
    page.screenshot(path=str(SCREENSHOTS_DIR / "02-cockpit-live-forward-mobile.png"), full_page=True)


def test_health_includes_v011_version(page: Page):
    """/health version 字段为 0.11.0."""
    resp = page.request.get(f"{BASE_URL}/health")
    assert resp.status == 200
    data = resp.json()
    assert data["version"] == "0.11.0"
