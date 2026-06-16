"""v0.7.2.1 赔率前端接入 - JS 行为单测(用 Playwright 跑真实浏览器)."""
import pytest


def test_odds_page_calls_service_status_endpoint(page, base_url):
    """T1: 打开 /#/odds 后,window._api_calls 应包含 /odds/service-status."""
    page.goto(f"{base_url}/#/odds", wait_until="domcontentloaded")
    # 等待 status-bar 出现表明页面渲染完成
    page.wait_for_selector('[data-testid="odds-status-bar"]', timeout=15000)

    api_calls = page.evaluate("() => window._api_calls || []")
    assert any("/odds/service-status" in c for c in api_calls), \
        f"Expected /odds/service-status in api calls, got: {api_calls}"


def test_odds_page_shows_model_value_bets_section(page, base_url):
    """T2: /#/odds 应渲染 [data-testid=odds-model-value-bets] section."""
    page.goto(f"{base_url}/#/odds", wait_until="domcontentloaded")
    page.wait_for_selector('[data-testid="odds-model-value-bets"]', timeout=15000)

    api_calls = page.evaluate("() => window._api_calls || []")
    assert any("/odds/value-bets-model" in c for c in api_calls), \
        f"Expected /odds/value-bets-model in api calls, got: {api_calls}"


def test_odds_card_model_dropdown_calls_compare_model(page, base_url):
    """T3: 切换赔率卡模型下拉应触发 /odds/compare-model?model=elo 调用."""
    page.goto(f"{base_url}/#/odds", wait_until="domcontentloaded")
    # 等待首屏渲染 + 卡片渲染
    page.wait_for_selector('[data-testid="odds-status-bar"]', timeout=15000)
    # 清空记录后切换
    page.evaluate("() => { window._api_calls = []; }")
    # 找到第一张赔率卡的下拉(select),切换为 elo
    page.evaluate("""() => {
        const sel = document.querySelector('select.bg-slate-950');
        if (sel) {
            sel.value = 'elo';
            sel.dispatchEvent(new Event('change'));
        }
    }""")
    # 给异步请求一点时间
    page.wait_for_timeout(1500)

    api_calls = page.evaluate("() => window._api_calls || []")
    assert any("/odds/compare-model" in c and "model=elo" in c for c in api_calls), \
        f"Expected /odds/compare-model?model=elo, got: {api_calls}"