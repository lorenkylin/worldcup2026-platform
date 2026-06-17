"""v0.7.9 Calibrated 4-th tab — Playwright E2E"""
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


def test_calibrated_endpoint_exposes_calibration_metrics(page):
    """T1: 端点暴露 calibration_metrics 字段, 含 3 个实测数"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?method=both")
    assert resp.status == 200
    data = resp.json()
    assert "calibration_metrics" in data
    metrics = data["calibration_metrics"]
    assert "platt_full_fit_pp" in metrics
    assert "platt_walkforward_80_20_pp" in metrics
    assert "isotonic_walkforward_80_20_pp" in metrics
    # 实测值均 < 1.5pp 门槛
    assert metrics["platt_full_fit_pp"] < 1.5
    assert metrics["platt_walkforward_80_20_pp"] < 1.5
    assert metrics["isotonic_walkforward_80_20_pp"] < 1.5
    # 都 > 0 (校准不是 placebo)
    assert metrics["platt_full_fit_pp"] > 0


def test_calibrated_cockpit_tab_visible(page):
    """T2: Elo 页 1v1 区 Calibrated tab 按钮可见 + 切换后渲染校准结果"""
    page.goto(f"{BASE_URL}/#/elo")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(3000)
    # 选主客队
    page.select_option("#elo-home", "BRA")
    page.select_option("#elo-away", "ARG")
    page.wait_for_timeout(2000)
    # Calibrated tab 按钮
    page.wait_for_selector("button:has-text('Calibrated')", timeout=10000)
    btn = page.locator("button:has-text('Calibrated')").first
    expect(btn).to_be_visible()
    # 点击切换
    btn.click()
    # 等 CalibratedPredict 渲染完成
    page.wait_for_timeout(6000)
    body_text = page.text_content("body")
    assert "Platt" in body_text, f"expected 'Platt' in body"
    assert "Iso" in body_text or "Isotonic" in body_text, f"expected 'Iso' in body"
    assert "experimental" in body_text.lower() or "实验性" in body


def test_calibrated_tab_response_matches_default(page):
    """T3: tab 默认 model=glicko2 method=both, 校准结果有 calibrated_probs + comparison"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?method=both&model=glicko2")
    data = resp.json()
    assert "calibrated_probs" in data
    assert "comparison" in data
    assert data["comparison"]["recommendation"] in ("platt", "isotonic")