"""v0.7.9 Calibrated tab 截图脚本 — desktop + mobile-375"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8000"
SHOTS_DIR = Path("D:/WorkBuddy/2026FIFA/worldcup2026-platform/docs/screenshots/v0.7.9")
SHOTS_DIR.mkdir(parents=True, exist_ok=True)


def capture_desktop():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/#/elo")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page.select_option("#elo-home", "BRA")
        page.select_option("#elo-away", "ARG")
        page.wait_for_timeout(2000)
        page.locator("button:has-text('Calibrated')").first.click()
        page.wait_for_timeout(6000)
        out = SHOTS_DIR / "01-elo-calibrated-desktop.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"[OK] {out}")
        browser.close()


def capture_mobile():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/#/elo")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page.select_option("#elo-home", "BRA")
        page.select_option("#elo-away", "ARG")
        page.wait_for_timeout(2000)
        page.locator("button:has-text('Calibrated')").first.click()
        page.wait_for_timeout(6000)
        out = SHOTS_DIR / "02-elo-calibrated-mobile-375.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"[OK] {out}")
        browser.close()


if __name__ == "__main__":
    capture_desktop()
    capture_mobile()