"""H5 5 页面截屏走查脚本.

执行：python tests/walkthrough.py
输出：D:/WorkBuddy/2026FIFA/worldcup2026-platform/data/screenshots/*.png
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "data" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8001"

# 5 个页面的 URL + 等待条件
PAGES = [
    ("01-home", "/", "今日赛程"),
    ("02-schedule", "/#/schedule", "全部赛程"),
    ("03-groups", "/#/groups", "小组赛积分榜"),
    ("04-teams", "/#/teams", "48 支参赛球队"),
    ("05-match-detail", "/#/match/1", "墨西哥"),
]


def main() -> int:
    """执行截屏走查."""
    failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        # 移动端尺寸（主人项目 H5 优先）
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        )
        page = context.new_page()

        for name, url, wait_text in PAGES:
            full_url = BASE_URL + url
            print(f"[{name}] GET {full_url}")
            try:
                page.goto(full_url, wait_until="networkidle", timeout=15000)
                # 等待目标文本出现（最长 5 秒）
                try:
                    page.wait_for_selector(f"text={wait_text}", timeout=5000)
                except Exception as exc:
                    print(f"  ⚠️  等待文本 '{wait_text}' 超时: {exc}")
                # 额外等 1 秒让渲染稳定
                time.sleep(1)
                screenshot_path = SCREENSHOT_DIR / f"{name}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"  ✅ {screenshot_path}")
            except Exception as exc:
                print(f"  ❌ {exc}")
                failed += 1

        # 错误页面（404）
        try:
            page.goto(BASE_URL + "/#/does-not-exist", wait_until="networkidle", timeout=10000)
            time.sleep(1)
            page.screenshot(path=str(SCREENSHOT_DIR / "06-not-found.png"), full_page=True)
        except Exception as exc:
            print(f"  ⚠️ 404 截图失败: {exc}")

        browser.close()
    return failed


if __name__ == "__main__":
    sys.exit(main())
