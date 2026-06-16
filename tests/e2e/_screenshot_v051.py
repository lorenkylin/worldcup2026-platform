"""Capture v0.5.1 screenshots for the completion report.

Outputs:
- docs/screenshots/v0.5.1/01-desktop-trend-chart.png
- docs/screenshots/v0.5.1/02-mobile-trend-chart.png
- docs/screenshots/v0.5.1/03-tab-draw.png
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots" / "v0.5.1"
OUT.mkdir(parents=True, exist_ok=True)


def cap_desktop():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8000/#/match/1", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        time.sleep(3)
        # 滚动到赔率走势图
        page.locator("#odds-trend-chart").scroll_into_view_if_needed()
        time.sleep(1)
        page.screenshot(path=str(OUT / "01-desktop-trend-chart.png"), full_page=True)
        # 切换到 客胜 tab 截图
        page.locator('.odds-trend-tab[data-metric="away_win"]').click()
        time.sleep(1.5)
        page.locator("#odds-trend-chart").scroll_into_view_if_needed()
        time.sleep(0.5)
        page.screenshot(path=str(OUT / "03-tab-away-win.png"), full_page=False)
        b.close()


def cap_mobile():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 375, "height": 800})
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8000/#/match/1", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        time.sleep(3)
        page.locator("#odds-trend-chart").scroll_into_view_if_needed()
        time.sleep(1)
        page.screenshot(path=str(OUT / "02-mobile-trend-chart.png"), full_page=True)
        b.close()


if __name__ == "__main__":
    cap_desktop()
    cap_mobile()
    print(f"[OK] Screenshots saved to {OUT}")
    for f in sorted(OUT.glob("*.png")):
        print(f"  - {f.name} ({f.stat().st_size // 1024}KB)")
