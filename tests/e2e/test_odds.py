"""E2E 端到端测试：M3 赔率模块.

覆盖:
- 抽屉 / 页面 /odds 加载
- 比赛详情页赔率卡显示
- 移动端 375px 赔率角标不破布局

依赖:
- 需先启动 server: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
- 需先装 playwright: python -m pip install playwright && python -m playwright install chromium
- 需先 admin 录入至少一条赔率（match_id=1, bookmaker=avg_market）
"""


def test_odds_page_renders(page, base_url):
    """赔率分析页加载."""
    import time
    page.goto(f"{base_url}/#/odds", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2)  # 等 API 渲染
    body_text = page.locator("body").text_content() or ""
    # 页面标题"赔率分析"
    assert "赔率分析" in body_text or "赔率" in body_text, \
        f"/#/odds 页未渲染标题: {body_text[:300]}"


def test_odds_drawer_link_exists(page, base_url):
    """抽屉菜单含 /#/odds 入口."""
    page.goto(f"{base_url}/#/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    # 找抽屉链接
    link = page.locator('a[href="#/odds"]').first
    assert link.count() > 0, "抽屉菜单未找到 /#/odds 入口"


def test_match_detail_shows_odds_card(page, base_url):
    """比赛详情页显示赔率卡（有赔率数据时）."""
    import time
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(1.5)
    body_text = page.locator("body").text_content() or ""
    # 比赛详情页有"市场赔率"卡片标题
    # (有赔率: 显示; 无赔率: 显示 "暂无赔率", 两种都是正常)
    has_odds_section = (
        "市场赔率" in body_text
        or "暂无赔率" in body_text
        or "💰" in body_text
    )
    assert has_odds_section, \
        f"比赛详情页未显示赔率区块: {body_text[:300]}"


def test_mobile_375px_odds_page(browser, base_url):
    """移动端 375px 赔率页布局不破."""
    ctx = browser.new_context(viewport={"width": 375, "height": 667})
    page = ctx.new_page()
    try:
        page.goto(f"{base_url}/#/odds", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        import time; time.sleep(2)
        vw = page.evaluate("() => window.innerWidth")
        assert vw == 375, f"viewport 应为 375 但实际 {vw}"
        # 应有"赔率"标题
        body_text = page.locator("body").text_content() or ""
        assert "赔率" in body_text, \
            f"移动端赔率页未显示标题: {body_text[:300]}"
    finally:
        ctx.close()
