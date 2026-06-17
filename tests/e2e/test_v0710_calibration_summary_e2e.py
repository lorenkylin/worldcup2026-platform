"""v0.7.10 Calibration Summary Cockpit mini-card - Playwright E2E"""
import pytest
from playwright.sync_api import sync_playwright, expect


BASE_URL = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="module")
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    yield pg
    ctx.close()


def test_calibration_summary_endpoint_exposes_6_fields(page):
    """T1: 轻量端点暴露 6 字段 (3 brier pp + samples + ttl + computed_at)"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibration-summary")
    assert resp.status == 200
    data = resp.json()
    assert data["training_samples"] == 913
    assert data["cache_ttl_seconds"] == 21600
    assert data["computed_at"].endswith("Z")
    assert isinstance(data["platt_full_fit_pp"], (int, float))
    assert isinstance(data["platt_walkforward_80_20_pp"], (int, float))
    assert isinstance(data["isotonic_walkforward_80_20_pp"], (int, float))
    # brier 改进百分点均 < 1.5pp 门槛
    for key in ("platt_full_fit_pp", "platt_walkforward_80_20_pp", "isotonic_walkforward_80_20_pp"):
        assert data[key] < 1.5, f"{key}={data[key]} 越过门槛"


def test_cockpit_renders_calibration_mini_card(page):
    """T2: Cockpit (/cockpit 路由) 渲染 v0.7.10 mini-card, 3 列 brier 速览"""
    page.goto(f"{BASE_URL}/#/cockpit", wait_until="networkidle")
    # 标题必须出现
    expect(page.get_by_text("G2 校准 brier 速览 (v0.7.10)")).to_be_visible(timeout=15000)
    # 3 列 card 标签
    expect(page.get_by_text("Platt Full Fit")).to_be_visible()
    expect(page.get_by_text("Platt 80/20 Walkforward")).to_be_visible()
    expect(page.get_by_text("Isotonic 80/20 Walkforward")).to_be_visible()
    # 训练样本 + 缓存文字
    expect(page.get_by_text("训练样本 913 场 · 缓存 6h")).to_be_visible()
