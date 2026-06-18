"""v0.14.2 Cockpit 去重设计 E2E 测试.

覆盖:
1. GET /api/cockpit/summary 返回聚合摘要
2. Cockpit 页面渲染新版核心区块（进度、KPI、数据健康、晋级、关键战、共识、分歧、Elo Top 5、快速入口）
"""


def test_cockpit_summary_endpoint(page, base_url):
    """GET /api/cockpit/summary 返回完整聚合字段."""
    resp = page.request.get(f"{base_url}/api/cockpit/summary")
    assert resp.status == 200, f"cockpit/summary 返回 {resp.status}"

    data = resp.json()
    assert "generated_at" in data
    assert "tournament_progress" in data
    assert "qualification_summary" in data
    assert "data_health" in data
    assert "critical_matches" in data
    assert "model_consensus" in data
    assert "market_model_divergence" in data
    assert "elo_top_teams" in data

    progress = data["tournament_progress"]
    assert "finished_matches" in progress
    assert "total_matches" in progress
    assert "completion_rate" in progress


def test_cockpit_page_renders_redesigned_sections(page, base_url):
    """新版 Cockpit 页面渲染去重后的核心区块，且不与详情页重复."""
    # 用完整页面刷新进入 cockpit，避免 hash 同文档导航时 router 渲染延迟
    page.goto(f"{base_url}/?_nocache=1#/cockpit", wait_until="domcontentloaded")

    # 顶栏与总览身份（驾驶舱聚合 API 可能耗时 >7s，给足等待）
    page.wait_for_selector("text=赛事总览驾驶舱", timeout=20000)
    page.wait_for_selector("text=统计 · 预览 · 关联（去重设计版）", timeout=20000)

    # 赛事进度 + KPI
    page.wait_for_selector("text=赛事进度")
    page.wait_for_selector("text=已完赛")
    page.wait_for_selector("text=场均进球")

    # 数据健康（包含旧“数据新鲜度”卡片兼容）
    page.wait_for_selector("text=数据源健康")
    page.wait_for_selector("text=数据新鲜度")

    # 晋级总览
    page.wait_for_selector("text=晋级 / 淘汰总览")
    page.wait_for_selector("text=基于当前积分榜 + 蒙特卡洛模拟")

    # 关键战
    page.wait_for_selector("text=未来 72 小时关键战")

    # 模型与市场
    page.wait_for_selector("text=模型高共识预测")
    page.wait_for_selector("text=市场 vs 模型分歧")

    # Elo Top 5 + 快速入口
    page.wait_for_selector("text=Elo 战力 Top 5")
    page.wait_for_selector("text=快速入口")
    page.wait_for_selector("text=赛程")
    page.wait_for_selector("text=积分榜")
    page.wait_for_selector("text=权重扫描 v0.7.4")

    # 截图归档
    page.screenshot(path="docs/screenshots/v0.14.2/01-cockpit-desktop.png", full_page=True)

    # 移动端不崩
    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_timeout(500)
    page.screenshot(path="docs/screenshots/v0.14.2/02-cockpit-mobile.png", full_page=True)
