"""v0.7.10 Cockpit mini-card 截图脚本 (desktop + mobile)"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path("docs/screenshots/v0.7.10")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        # desktop
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(f"{BASE}/#/cockpit", wait_until="networkidle")
        page.wait_for_timeout(800)  # 等 mini-card 数据填充
        page.screenshot(path=str(OUT / "01-cockpit-calibration-card-desktop.png"), full_page=False)
        print(f"saved: {OUT / '01-cockpit-calibration-card-desktop.png'}")
        ctx.close()
        # mobile
        ctx = b.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        page.goto(f"{BASE}/#/cockpit", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "02-cockpit-calibration-card-mobile-375.png"), full_page=False)
        print(f"saved: {OUT / '02-cockpit-calibration-card-mobile-375.png'}")
        ctx.close()
        b.close()


if __name__ == "__main__":
    sys.exit(main())
