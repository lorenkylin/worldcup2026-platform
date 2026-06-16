"""v0.7.2.3 赔率走势对比 - 端到端页面测试."""
import time


def test_match_detail_calls_history_comparison_endpoint(page, base_url):
    """打开 match detail 后,/odds/{id}/history-comparison 端点会被调用."""
    # 等服务器 ready
    page.wait_for_load_state("domcontentloaded")

    # 监听 API 调用
    page.evaluate("""() => { window._api_calls = []; const orig = window.fetch;
        window.fetch = function(...args) { window._api_calls.push(args[0]); return orig.apply(this, args); };
    }""")

    # 找 match 链接 → navigate → 等
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    time.sleep(3)

    calls = page.evaluate("() => window._api_calls || []")
    has_call = any("/history-comparison" in str(c) for c in calls)
    # 端点可能 204,但只要发起过调用即视为接入
    assert has_call, f"未找到 /history-comparison 调用. calls={calls[:5]}"


def test_match_detail_shows_odds_model_history_card(page, base_url):
    """match detail 页应出现 '赔率 vs 模型概率走势' 卡片."""
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    time.sleep(2)

    # 卡片标题 v0.7.2.3
    title_visible = page.evaluate("""() => {
        const titles = Array.from(document.querySelectorAll('h3'));
        return titles.some(t => t.textContent && t.textContent.includes('赔率 vs 模型概率走势'));
    }""")
    assert title_visible, "未找到 '赔率 vs 模型概率走势' 卡片"


def test_match_detail_model_select_has_three_options(page, base_url):
    """模型下拉有 Elo/Glicko-2/Blend 三个选项."""
    page.goto(f"{base_url}/#/match/1", wait_until="domcontentloaded")
    time.sleep(2)

    options = page.evaluate("""() => {
        const sel = document.getElementById('odds-model-select');
        if (!sel) return null;
        return Array.from(sel.options).map(o => o.value);
    }""")
    assert options is not None, "未找到 #odds-model-select"
    assert set(options) == {"elo", "glicko2", "blend"}
