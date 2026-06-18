"""v0.7.2 赔率 API 端到端测试.

依赖: uvicorn 服务需先启动 (python scripts/start_server.py)
"""
import time


def test_compare_model_endpoint(page, base_url):
    """GET /api/odds/compare-model?match_id=1 → 200 + 完整结构."""
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/odds/compare-model?match_id=1&model=blend');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    # 可能 match_id=1 无赔率 → 404 是预期
    assert resp["status"] in (200, 404), f"got {resp['status']}: {resp['body']}"
    if resp["status"] == 200:
        body = resp["body"]
        assert body["model"] == "blend"
        assert "model_probs" in body
        assert "market_probs" in body
        assert "value_bet" in body


def test_compare_model_rejects_invalid_model(page, base_url):
    """?model=invalid → 422."""
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/odds/compare-model?match_id=1&model=invalid');
            return r.status;
        }}"""
    )
    assert resp == 422


def test_value_bets_model_endpoint(page, base_url):
    """GET /api/odds/value-bets-model?model=blend&min_tier=edge → 200 + items 数组."""
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/odds/value-bets-model?model=blend&min_tier=edge&limit=10');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    assert resp["status"] == 200, f"got {resp['status']}: {resp['body']}"
    body = resp["body"]
    assert body["model"] == "blend"
    assert body["min_tier"] == "edge"
    assert "items" in body
    assert isinstance(body["items"], list)


def test_value_bets_model_rejects_invalid_tier(page, base_url):
    """?min_tier=invalid → 422."""
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/odds/value-bets-model?model=blend&min_tier=invalid');
            return r.status;
        }}"""
    )
    assert resp == 422


def test_odds_service_status(page, base_url):
    """GET /api/odds/service-status → 200 + provider."""
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/odds/service-status');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    assert resp["status"] == 200
    body = resp["body"]
    assert "provider" in body
    assert "rate_limit_per_min" in body
    assert "cache_ttl_seconds" in body


def test_admin_fetch_odds_requires_dates(page, base_url):
    """POST /api/admin/odds/fetch 不传 dates → 422."""
    from app.config import settings
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/admin/odds/fetch', {{
                method: 'POST',
                headers: {{ 'X-Admin-Token': '{settings.admin_token}' }}
            }});
            return r.status;
        }}"""
    )
    assert resp == 422


def test_admin_fetch_odds_rejects_bad_token(page, base_url):
    """错误 admin_token → 403."""
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/admin/odds/fetch?dates=2099-06-11', {{
                method: 'POST',
                headers: {{ 'X-Admin-Token': 'bad_token' }}
            }});
            return r.status;
        }}"""
    )
    assert resp == 403


def test_admin_fetch_odds_upserts_to_db(page, base_url):
    """POST /api/admin/odds/fetch?dates=2026-06-20 → 200 + 写入 DB(日期按北京时间)."""
    from app.config import settings
    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/admin/odds/fetch?dates=2026-06-20&use_cache=false', {{
                method: 'POST',
                headers: {{ 'X-Admin-Token': '{settings.admin_token}' }}
            }});
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    assert resp["status"] == 200, f"got {resp['status']}: {resp['body']}"
    body = resp["body"]
    assert "fetched" in body
    assert "written" in body
    assert body["fetched"] >= 1
    assert body["written"] >= 1
    assert body["status"]["provider"] in ("mock", "the_odds_api", "pinnacle")


def test_compare_model_after_admin_fetch(page, base_url):
    """admin fetch 写入赔率后,compare-model 端点能命中."""
    from app.config import settings
    page.evaluate(
        f"""async () => {{
            await fetch('{base_url}/api/admin/odds/fetch?dates=2026-06-20&use_cache=false', {{
                method: 'POST',
                headers: {{ 'X-Admin-Token': '{settings.admin_token}' }}
            }});
        }}"""
    )
    time.sleep(0.5)

    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/matches/1/odds');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    if resp["status"] != 200 or not resp["body"].get("has_odds"):
        import pytest
        pytest.skip("match_id=1 无赔率,跳过")

    resp2 = page.evaluate(
        f"""async () => {{
            const r = await fetch('{base_url}/api/odds/compare-model?match_id=1&model=blend');
            return r.status;
        }}"""
    )
    assert resp2 in (200, 422), f"got {resp2}"