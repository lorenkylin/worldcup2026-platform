"""Capture v0.6.0 screenshots for the completion report.

Outputs:
- docs/screenshots/v0.6.0/01-cockpit-desktop.png        (G1: 模型准确率 mini-card)
- docs/screenshots/v0.6.0/02-accuracy-desktop.png        (G2: 3 模型横评表)
- docs/screenshots/v0.6.0/03-odds-desktop.png           (G3: 数据更新时间)
- docs/screenshots/v0.6.0/04-accuracy-mobile.png         (移动端)
- docs/screenshots/v0.6.0/05-odds-mobile.png             (移动端)
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots" / "v0.6.0"
OUT.mkdir(parents=True, exist_ok=True)


def cap_desktop():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()

        # 1. Cockpit — 模型准确率 mini-card (G1)
        page.goto("http://127.0.0.1:8000/#/cockpit", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(5)  # 等 6 个 API 完成
        page.screenshot(path=str(OUT / "01-cockpit-desktop.png"), full_page=True)
        print("[01-cockpit-desktop.png] saved")

        # 2. Accuracy dashboard — 3 模型横评表 (G2)
        page.goto("http://127.0.0.1:8000/#/accuracy", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)
        page.screenshot(path=str(OUT / "02-accuracy-desktop.png"), full_page=True)
        print("[02-accuracy-desktop.png] saved")

        # 3. Odds — 数据更新时间 (G3)
        page.goto("http://127.0.0.1:8000/#/odds", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)
        page.screenshot(path=str(OUT / "03-odds-desktop.png"), full_page=True)
        print("[03-odds-desktop.png] saved")

        b.close()


def cap_mobile():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()

        # 4. Accuracy mobile
        page.goto("http://127.0.0.1:8000/#/accuracy", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)
        page.screenshot(path=str(OUT / "04-accuracy-mobile.png"), full_page=True)
        print("[04-accuracy-mobile.png] saved")

        # 5. Odds mobile
        page.goto("http://127.0.0.1:8000/#/odds", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)
        page.screenshot(path=str(OUT / "05-odds-mobile.png"), full_page=True)
        print("[05-odds-mobile.png] saved")
        b.close()


if __name__ == "__main__":
    cap_desktop()
    cap_mobile()
    print("All v0.6.0 screenshots done")

