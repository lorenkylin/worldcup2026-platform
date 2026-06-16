"""v0.7.5 Adaptive Weight E2E 测试."""


def test_adaptive_endpoint_returns_segment_and_weights(page, base_url):
    """E1: 端点返回 segment/w_elo/w_g2 字段."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/adaptive-weight/BRA/ARG');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200
    body = resp["body"]
    assert body["home"] == "BRA"
    assert body["away"] == "ARG"
    assert "segment" in body
    assert body["segment"] in ["fresh", "warm", "stale", "dormant"]
    assert "w_elo" in body
    assert "w_g2" in body
    assert abs(body["w_elo"] + body["w_g2"] - 1.0) < 0.01
    assert "rationale" in body
    assert "blend_result" in body


def test_elo_page_3tab_includes_adaptive(page, base_url):
    """E2: /elo 路由 1v1 对比器 4-tab 含 Adaptive 按钮."""
    # 先离开 cockpit,强制重渲 /elo
    page.goto("about:blank")
    page.goto(f"{base_url}/#/elo", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    found = page.evaluate("() => Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('Adaptive'))")
    assert found, "Adaptive 按钮未渲染"


def test_adaptive_endpoint_invalid_team_returns_404(page, base_url):
    """E3: 球队不存在 → 404."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/adaptive-weight/XXX_FAKE/YYY_FAKE');
            return r.status;
        }"""
    )
    assert resp == 404
