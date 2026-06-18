"""v0.7.4 weight sweep E2E 测试."""


def test_weight_sweep_endpoint_returns_winner(page, base_url):
    """/api/elo/weight-sweep 返回 winner 字段."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/weight-sweep');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200
    body = resp["body"]
    assert body["n_matches"] == 913
    assert body["weights_evaluated"] == 7
    assert "winner" in body
    assert body["winner"]["metric_used"] == "brier"
    # 已知结论: G2 单独最优
    assert body["winner"]["w_elo"] == 0.0
    assert body["winner"]["w_g2"] == 1.0


def test_cockpit_shows_weight_sweep_mini_card(page, base_url):
    """Cockpit 页面通过快速入口展示权重扫描."""
    # 用完整页面刷新进入 cockpit，避免 hash 同文档导航时 router 渲染延迟
    page.goto(f"{base_url}/?_nocache=1#/cockpit", wait_until="domcontentloaded")
    page.wait_for_selector("text=权重扫描 v0.7.4", timeout=15000)
    page.wait_for_selector("text=最佳权重", timeout=15000)


def test_weight_sweep_baseline_matches_v070a_default(page, base_url):
    """baseline_50_50 accuracy 是 v0.7.0a 默认权重的实测值."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/weight-sweep');
            return await r.json();
        }"""
    )
    baseline = resp["baseline_50_50"]
    assert baseline["w_elo"] == 0.5
    assert 0.60 <= baseline["accuracy"] <= 0.62
    assert 0.52 <= baseline["brier"] <= 0.54
