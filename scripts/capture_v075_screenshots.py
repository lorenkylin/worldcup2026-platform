"""v0.7.5 截图脚本: Adaptive tab 桌面 + 移动端."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "docs" / "screenshots" / "v0.7.5"
OUT.mkdir(parents=True, exist_ok=True)


def capture_desktop():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8000/#/elo", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        # 点 Adaptive tab
        page.evaluate("setEloModel('adaptive')")
        page.wait_for_timeout(2500)
        # 滚到 1v1 区域
        page.evaluate("document.querySelector('#elo-predict-result')?.scrollIntoView({behavior:'instant', block:'center'})")
        page.wait_for_timeout(500)
        out = OUT / "01-elo-adaptive-desktop.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"OK: {out}")
        b.close()


def capture_mobile():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8000/#/elo", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        page.evaluate("setEloModel('adaptive')")
        page.wait_for_timeout(2500)
        out = OUT / "02-elo-adaptive-mobile-375.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"OK: {out}")
        b.close()


if __name__ == "__main__":
    if "mobile" in sys.argv:
        capture_mobile()
    else:
        capture_desktop()
