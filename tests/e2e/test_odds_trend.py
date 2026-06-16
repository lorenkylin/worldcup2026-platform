"""v0.5.1 赔率走势图表 E2E 测试.

依赖:
- 需先启动 server: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
- 需先装 playwright: python -m pip install playwright && python -m playwright install chromium
- 需先有 match_id=1 的赔率数据(走 admin 或种子)
"""

import time


def test_odds_trend_canvas_renders(page, base_url):
    """比赛详情页加载后,赔率走势图 canvas 出现."""
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    # 等 chart.js 加载 + 渲染
    time.sleep(2.5)
    # 检查 canvas 存在
    canvas = page.locator("#odds-trend-chart")
    assert canvas.count() > 0, "赔率走势图 canvas 不存在"


def test_odds_trend_has_tabs(page, base_url):
    """走势图有 主胜/平/客胜 三个 tab."""
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2.5)
    # 三个 tab
    home_tab = page.locator('.odds-trend-tab[data-metric="home_win"]')
    draw_tab = page.locator('.odds-trend-tab[data-metric="draw"]')
    away_tab = page.locator('.odds-trend-tab[data-metric="away_win"]')
    assert home_tab.count() == 1, "主胜 tab 缺失"
    assert draw_tab.count() == 1, "平 tab 缺失"
    assert away_tab.count() == 1, "客胜 tab 缺失"


def test_odds_trend_tab_switch(page, base_url):
    """点击 平 tab 切换 datasets,主胜 tab 失去高亮."""
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2.5)
    # 默认主胜 tab 高亮
    home_tab = page.locator('.odds-trend-tab[data-metric="home_win"]')
    draw_tab = page.locator('.odds-trend-tab[data-metric="draw"]')
    home_classes = home_tab.get_attribute("class") or ""
    assert "bg-cyan-500" in home_classes, "主胜 tab 默认未高亮"
    # 点击平 tab
    draw_tab.click()
    time.sleep(0.5)
    draw_classes = draw_tab.get_attribute("class") or ""
    assert "bg-cyan-500" in draw_classes, "点击后平 tab 未高亮"
    home_classes_after = home_tab.get_attribute("class") or ""
    assert "bg-cyan-500" not in home_classes_after, "主胜 tab 仍高亮"


def test_odds_trend_mobile_375(browser, base_url):
    """移动端 375px 走势图布局不破."""
    ctx = browser.new_context(viewport={"width": 375, "height": 667})
    page = ctx.new_page()
    try:
        page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        time.sleep(2.5)
        vw = page.evaluate("() => window.innerWidth")
        assert vw == 375, f"viewport 应为 375 但实际 {vw}"
        # canvas 应在 viewport 内(无水平滚动)
        canvas = page.locator("#odds-trend-chart")
        assert canvas.count() > 0, "移动端赔率走势图 canvas 不存在"
        # 检查容器不超出
        card = page.locator("text=赔率走势").first
        if card.count() > 0:
            box = card.bounding_box()
            if box:
                assert box["x"] >= 0, f"card x={box['x']} 应 >= 0"
                assert box["x"] + box["width"] <= 375, f"card 超出 375px viewport"
    finally:
        ctx.close()
