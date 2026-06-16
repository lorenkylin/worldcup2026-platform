"""v0.7.4 截图 — Cockpit weight-sweep mini-card 桌面 + 移动."""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = Path("docs/screenshots/v0.7.4")


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for label, viewport in [
            ("01-cockpit-weight-sweep-desktop", {"width": 1440, "height": 900}),
            ("02-cockpit-weight-sweep-mobile-375", {"width": 375, "height": 812}),
        ]:
            ctx = await browser.new_context(viewport=viewport)
            page = await ctx.new_page()
            await page.goto(f"{BASE_URL}/#/cockpit", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(OUT_DIR / f"{label}.png"), full_page=False)
            print(f"saved {label}.png")
            await ctx.close()
        await browser.close()


asyncio.run(main())
