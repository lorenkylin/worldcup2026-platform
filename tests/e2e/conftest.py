"""E2E 测试共享配置：base URL + 浏览器 fixture."""

import os
import sys
from pathlib import Path

import pytest

# 让 pytest 能 import app.*
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


BASE_URL = os.environ.get("WC26_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def base_url() -> str:
    """后端服务地址."""
    return BASE_URL


@pytest.fixture(scope="module")
def browser():
    """共用一个 chromium browser，session-scoped 减少启动开销."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, base_url):
    """每个测试一个干净的 page（移动端 375 默认）."""
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
    )
    page = ctx.new_page()
    page.goto(base_url, wait_until="domcontentloaded")
    yield page
    ctx.close()
