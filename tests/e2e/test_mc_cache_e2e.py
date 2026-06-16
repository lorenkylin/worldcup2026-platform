"""v0.7.1.1 Monte Carlo 缓存 E2E 测试.

依赖: 服务需先启动 (uvicorn app.main:app --port 8000)
"""
import time


def test_mc_cache_second_request_is_faster(page, base_url):
    """同一默认参数连点 2 次,第二次响应时间 < 500ms."""
    url = f"{base_url}/api/simulator/tournament?simulations=1000&model=blend&seed=42"

    # 第一次:可能 miss,计算并缓存
    t0 = time.time()
    resp1 = page.evaluate(
        f"""async () => {{
            const r = await fetch('{url}');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    duration1 = time.time() - t0
    assert resp1["status"] == 200, f"first got {resp1['status']}"

    # 第二次:应命中缓存
    t0 = time.time()
    resp2 = page.evaluate(
        f"""async () => {{
            const r = await fetch('{url}');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    duration2 = time.time() - t0
    assert resp2["status"] == 200, f"second got {resp2['status']}"
    assert duration2 < 0.5, f"cached request took {duration2:.2f}s, expected < 0.5s"
    assert resp2["body"].get("cached") is True
    assert resp2["body"]["champion_distribution"] == resp1["body"]["champion_distribution"]


def test_mc_refresh_param_recomputes(page, base_url):
    """?refresh=1 强制重算,不命中缓存."""
    url_hit = f"{base_url}/api/simulator/tournament?simulations=1000&model=blend&seed=42"
    # 先命中一次缓存
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{url_hit}');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    assert resp["status"] == 200

    # refresh=1 强制重算
    url_refresh = f"{url_hit}&refresh=1"
    t0 = time.time()
    resp2 = page.evaluate(
        f"""async () => {{
            const r = await fetch('{url_refresh}');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    duration = time.time() - t0
    assert resp2["status"] == 200
    assert resp2["body"].get("cached") is not True
    assert duration > 0.3, f"refresh should recompute, but took {duration:.2f}s"
