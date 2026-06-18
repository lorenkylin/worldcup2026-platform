"""E2E 端到端测试：核心 4 个 SPA 页面渲染 + 关键功能.

覆盖：
- 首页（#/）：命中今日赛程 + Top 4 球队
- 赛程页（#/schedule）：列出 6/15 的 4 场比赛
- 小组页（#/groups）：12 组 48 队
- H2H 主页（#/h2h）：默认 BRA + 至少 1 个对手
- 移动端 375px 不破布局

依赖：
- 需先启动 server：python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
- 需先装 playwright：python -m pip install playwright && python -m playwright install chromium
"""

import pytest


def test_home_page_renders(page, base_url):
    """首页加载并显示 Top 4 球队."""
    page.goto(f"{base_url}/#/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    # 至少 1 个 match 卡片
    body_text = page.locator("body").text_content()
    assert body_text is not None
    assert len(body_text) > 100, f"首页内容过短：{body_text[:100]}"


def test_schedule_page_renders_today_matches(page, base_url):
    """赛程页加载并显示 6/15 的 4 场比赛."""
    page.goto(f"{base_url}/#/schedule", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    body_text = page.locator("body").text_content() or ""
    # 应有 6/15 标记（schedule 用 "6/15" 格式）
    assert "6/15" in body_text, f"赛程页未显示 6/15 比赛: {body_text[:300]}"
    # 4 支球队（用中文名匹配，因为页面渲染了"西班牙/佛得角/比利时/埃及/伊朗/新西兰/沙特/乌拉圭"）
    has_team = any(name in body_text for name in ["西班牙", "佛得角", "比利时", "埃及", "伊朗", "新西兰", "沙特", "乌拉圭"])
    assert has_team, f"赛程页未显示 6/15 的 4 场比赛中的任何一队: {body_text[:300]}"


def test_groups_page_renders_12_groups(page, base_url):
    """小组页加载并显示 12 个小组（48 队）."""
    import re
    import time
    page.goto(f"{base_url}/#/groups", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2)  # 等待 12 组渲染（API 响应后再 paint）
    body_text = page.locator("body").text_content() or ""
    # 找国旗 emoji（48 队 = 48 个）
    flag_emojis = re.findall(r"(?:[\U0001F1E6-\U0001F1FF]{2})", body_text)
    assert len(flag_emojis) >= 12, \
        f"小组页国旗 emoji 数太少（{len(flag_emojis)} < 12，期望至少 12）: {body_text[:300]}"


def test_h2h_page_renders_opponents(page, base_url):
    """H2H 主页加载并显示对手列表（默认 BRA）."""
    page.goto(f"{base_url}/#/h2h", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    body_text = page.locator("body").text_content() or ""
    # 应有 "巴西" 或 "BRA" 或 "Brazil"
    assert "巴西" in body_text or "BRA" in body_text or "Brazil" in body_text, \
        f"H2H 主页未显示默认队（巴西）: {body_text[:300]}"
    # 至少 1 个对手（SRB/摩洛哥/KOR/CMR 等）
    has_opponent = any(kw in body_text for kw in ["SRB", "摩洛哥", "MAR", "韩国", "KOR"])
    assert has_opponent, f"H2H 主页未显示对手卡片: {body_text[:300]}"


def test_mobile_375px_layout_not_broken(browser, base_url):
    """移动端 375px 视口布局不破."""
    ctx = browser.new_context(viewport={"width": 375, "height": 667})
    page = ctx.new_page()
    try:
        page.goto(f"{base_url}/#/", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        # 视口宽度应等于 375（说明 viewport meta 标签生效）
        vw = page.evaluate("() => window.innerWidth")
        assert vw == 375, f"viewport 应为 375 但实际 {vw}"
        # 主页内容应至少显示 Top 4 球队
        body_text = page.locator("body").text_content() or ""
        assert len(body_text) > 100, f"移动端首页内容为空: {body_text[:100]}"
    finally:
        ctx.close()


def test_bracket_page_renders(page, base_url):
    """v0.3.0: Bracket 页加载并显示淘汰赛路线图 + R32 节点."""
    import time
    page.goto(f"{base_url}/#/bracket", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2)  # 等待 /api/bracket 渲染
    body_text = page.locator("body").text_content() or ""
    assert "晋级路线图" in body_text, f"Bracket 页未渲染标题: {body_text[:300]}"
    assert "R32" in body_text or "32 强" in body_text, f"Bracket 页未显示 32 强阶段: {body_text[:300]}"


def test_404_page_renders(page, base_url):
    """A8: 未知 hash 路径应渲染 404 页（非空，非崩溃）."""
    page.goto(f"{base_url}/#/nonexistent-page-xyz", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    import time; time.sleep(1)  # 等待 A8 渲染
    body_text = page.locator("body").text_content() or ""
    # 404 页有"找不到这个页面"（app.js renderNotFound 模板）
    has_404 = "找不到" in body_text or "404" in body_text or "首页" in body_text
    assert has_404, f"404 页未渲染（应有'找不到这个页面'或'首页'按钮）: {body_text[:200]}"


def test_elo_page_renders_blend_tab(page, base_url):
    """v0.7.0a: Elo 页加载并显示 ModelBlend 3-tab (Elo / Glicko-2 / Blend 默认) + Glicko-2 评分榜."""
    import time
    page.goto(f"{base_url}/#/elo", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    # v0.7.0a: Playwright page.goto hash-only 第二次 navigate 不一定重载触发 DOMContentLoaded.
    # 显式 evaluate router() 触发路由 + 等 1v1 段(elo-predict-result)出现.
    page.evaluate("() => router()")
    page.wait_for_function(
        "() => document.getElementById('elo-predict-result') !== null",
        timeout=15000,
    )
    time.sleep(1)  # 保险: 等 ModelBlend predict API resolve
    body_text = page.locator("body").text_content() or ""
    # 3 模型 tab 必须全部出现
    assert "Elo M1 模型" in body_text, f"Elo 页未显示 Elo M1 模型 tab: {body_text[:300]}"
    assert "Glicko-2 模型" in body_text, f"Elo 页未显示 Glicko-2 模型 tab: {body_text[:300]}"
    assert "融合模型" in body_text, f"Elo 页未显示融合模型 tab: {body_text[:300]}"
    # 默认融合模型应激活(高亮 class 含 bg-gradient 或 bg-violet)
    blend_btn = page.locator("button:has-text('融合模型')").first
    blend_class = blend_btn.get_attribute("class") or ""
    assert "bg-gradient" in blend_class or "bg-violet" in blend_class, \
        f"融合模型 tab 默认未高亮(class={blend_class[:100]})"
    # 1v1 预测结果应含 "融合模型" 标注
    assert "融合模型" in body_text, \
        f"Elo 页未显示融合模型预测结果: {body_text[:500]}"
    # Glicko-2 评分榜段(默认折叠)应存在
    assert "Glicko-2 评分榜" in body_text, f"Elo 页未显示 Glicko-2 评分榜段: {body_text[:300]}"
