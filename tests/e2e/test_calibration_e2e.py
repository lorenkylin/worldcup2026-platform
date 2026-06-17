"""v0.7.8 G2-only Platt scaling - 3 E2E tests"""
import re
from pathlib import Path

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


def test_calibrated_predict_endpoint_returns_calibrated_probs(page):
    """T1: 端点 /api/elo/calibrated-predict/BRA/ARG 返回 calibrated_probs"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?model=glicko2")
    assert resp.status == 200, f"expected 200 got {resp.status}: {resp.text()}"
    data = resp.json()
    assert "calibrated_probs" in data
    assert "raw_probs" in data
    assert "calibration_params" in data
    assert data["experimental"] is True
    assert data["training_samples"] == 913
    # 三元组归一化
    c = data["calibrated_probs"]
    s = c["home"] + c["draw"] + c["away"]
    assert abs(s - 1.0) < 0.01, f"calibrated_probs sum={s} not 1.0"


def test_calibrated_predict_supports_three_models(page):
    """T2: 端点支持 model=glicko2/elo/blend 三种参数"""
    for m in ["glicko2", "elo", "blend"]:
        resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?model={m}")
        assert resp.status == 200, f"{m}: {resp.status} {resp.text()}"
        data = resp.json()
        assert data["model"] == m
        assert data["calibrated_probs"]["home"] > 0


def test_calibrated_predict_brier_improvement_positive(page):
    """T3: 端点暴露 brier_improvement 字段,值=0.0069 (full sample),说明 calibration 优于 raw"""
    resp = page.request.get(f"{BASE_URL}/api/elo/calibrated-predict/BRA/ARG?model=glicko2")
    data = resp.json()
    assert "brier_improvement" in data
    # 实验性功能,brier 改进 > 0 (calibration 不是 placebo)
    assert data["brier_improvement"] > 0
