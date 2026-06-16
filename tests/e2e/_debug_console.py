"""Debug helper: capture console + network for #/match/1."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    page.on("console", lambda msg: print(f"[CONSOLE {msg.type}] {msg.text[:200]}"))
    page.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}"))
    page.on("requestfailed", lambda req: print(f"[REQ FAIL] {req.url} - {req.failure}"))

    page.goto("http://127.0.0.1:8000/#/match/1", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(3)
    print("=== HTML BODY ===")
    print(page.locator("#app").inner_html()[:2000])
    print("=== COUNT canvases ===")
    print(page.locator("canvas").count())
    print("=== COUNT odds-trend-canvas ===")
    print(page.locator("#odds-trend-chart").count())

    browser.close()
