"""E2E 测试共享配置：base URL + 浏览器 fixture."""

import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# 让 pytest 能 import app.*
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


BASE_URL = os.environ.get("WC26_BASE_URL", "http://127.0.0.1:8000")


def _wait_for_server(base_url: str, timeout: float = 60.0, interval: float = 0.5) -> None:
    """Poll /health until the backend accepts connections or timeout is reached."""
    health_url = f"{base_url.rstrip('/')}/health"
    deadline = time.monotonic() + timeout
    last_err = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_err = exc
        time.sleep(interval)
    raise RuntimeError(f"Server not ready at {health_url!r} after {timeout}s: {last_err}")


def pytest_collection_modifyitems(config, items):
    """自动给 tests/e2e 目录下所有测试加 @pytest.mark.e2e."""
    e2e_marker = pytest.mark.e2e
    for item in items:
        if item.nodeid.startswith("tests/e2e/"):
            item.add_marker(e2e_marker)


@pytest.fixture(autouse=True)
def _temp_db():
    """E2E 测试使用生产数据库(与 uvicorn 服务一致),覆盖 tests/conftest.py 的临时 DB.

    E2E 测试只读 API,不写入数据,因此共享生产 DB 安全。
    """
    yield


@pytest.fixture(scope="module")
def base_url() -> str:
    """后端服务地址."""
    return BASE_URL


@pytest.fixture(scope="module", autouse=True)
def _server_ready(base_url):
    """Ensure uvicorn is warm before the first E2E navigation."""
    _wait_for_server(base_url)


@pytest.fixture(scope="module")
def browser():
    """共用一个 chromium browser，session-scoped 减少启动开销."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # 禁用 Service Worker，避免静态资源缓存导致测试拿到旧版 app.js/sw.js
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-features=ServiceWorker"],
        )
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
    page.set_default_navigation_timeout(60_000)
    # 预加载 base_url，给相对 fetch 提供 origin；加 nocache 避免拿到旧版 index.html/app.js
    page.goto(f"{base_url}?_nocache=1", wait_until="domcontentloaded")
    yield page
    ctx.close()
