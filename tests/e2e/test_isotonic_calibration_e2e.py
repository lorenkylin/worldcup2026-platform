"""v0.7.8.1 Isotonic 校准对比 — Playwright E2E"""
import pytest
from playwright.sync_api import sync_playwright


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


def test_calibrated_predict_default_still_works(page):
    """默认 method=platt 行为不变 — 主输出是 platt 校准, isotonic 字段不出现"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG")
    assert resp.status == 200
    data = resp.json()
    assert "calibrated_probs" in data
    assert data["experimental"] is True
    assert "isotonic" not in data
    # platt 是 v0.7.9 改造后保留的字段 (便于前端 A/B), 主输出 calibrated_probs 等于 platt
    if "platt" in data:
        assert data["calibrated_probs"] == data["platt"]["calibrated_probs"]
    assert "brier_improvement" in data


def test_calibrated_predict_method_isotonic(page):
    """?method=isotonic 返回 isotonic 校准结果"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?method=isotonic")
    assert resp.status == 200
    data = resp.json()
    assert "isotonic" in data
    cal = data["isotonic"]["calibrated_probs"]
    assert abs(cal["home"] + cal["draw"] + cal["away"] - 1.0) < 1e-6
    assert data["calibrated_probs"] == cal  # method=isotonic 时主输出就是 isotonic


def test_calibrated_predict_method_both(page):
    """?method=both 同时返回 platt + isotonic + comparison"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?method=both")
    assert resp.status == 200
    data = resp.json()
    assert "platt" in data
    assert "isotonic" in data
    assert "comparison" in data
    assert data["comparison"]["recommendation"] in ("platt", "isotonic")
    assert isinstance(data["comparison"]["platt_brier_pp"], (int, float))
    assert isinstance(data["comparison"]["isotonic_brier_pp"], (int, float))


def test_calibrated_predict_method_invalid_422(page):
    """?method=foo 应返回 422"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?method=foo")
    assert resp.status == 422