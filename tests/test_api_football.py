"""API-Football 客户端单元测试（v0.14.0）.

用 httpx.MockTransport 注入 mock handler，验证:
- 限速 + 日预算 + 缓存 + 错误分类
- 不实际访问 API-Football
"""
import time
from unittest.mock import patch

import httpx
import pytest

from app.services.api_football import (
    ApiFootballClient,
    ApiFootballHttpError,
    ApiKeyMissingError,
    RateLimitedError,
    fifa_code_from_team_name,
    normalize_team_name,
)


def _make_handler(responses):
    """构造 httpx.MockTransport 的 handler.

    Args:
        responses: list[(status, body)], handler 按调用顺序消费.
    """
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        if idx >= len(responses):
            return httpx.Response(404, json={"message": "no more mock responses"})
        status, body = responses[idx]
        # 模拟 API-Football 标准响应包装
        wrapped = {"response": body, "errors": []}
        return httpx.Response(status, json=wrapped)

    return handler, call_count


def _mock_client(responses, **kwargs) -> ApiFootballClient:
    """构造带 mock transport 的客户端."""
    handler, call_count = _make_handler(responses)
    kwargs.setdefault("api_key", "test_token")
    kwargs.setdefault("cache_ttl_seconds", 60)
    client = ApiFootballClient(_transport=httpx.MockTransport(handler), **kwargs)
    client._test_call_count = call_count
    return client


def test_no_api_key_raises_immediately():
    """无 api_key 时直接抛错，不消耗配额."""
    client = ApiFootballClient(api_key="")
    with pytest.raises(ApiKeyMissingError) as exc:
        client.get_fixtures()
    assert "未配置" in str(exc.value)
    assert client._daily_requests == 0


def test_cache_hit_within_ttl():
    """缓存命中：第二次调用不发请求."""
    client = _mock_client([(200, [{"fixture": 1}])])
    a = client.get_fixtures(date_from="2026-06-11", date_to="2026-06-12")
    b = client.get_fixtures(date_from="2026-06-11", date_to="2026-06-12")
    assert a == b == [{"fixture": 1}]
    assert client._test_call_count["n"] == 1


def test_different_params_different_cache_keys():
    """不同 params 缓存隔离."""
    client = _mock_client([(200, [{"id": 1}]), (200, [{"id": 2}])])
    a = client.get_fixtures(date_from="2026-06-11", date_to="2026-06-12")
    b = client.get_fixtures(date_from="2026-06-13", date_to="2026-06-14")
    assert a == [{"id": 1}]
    assert b == [{"id": 2}]
    assert client._test_call_count["n"] == 2


def test_rate_limit_triggers_sleep():
    """超过 rate_limit_per_min 时 sleep."""
    client = _mock_client([(200, [{"id": i}]) for i in range(10)], rate_limit_per_min=3)
    for i in range(3):
        client.get_fixtures(date_from=f"2026-06-{11+i}", date_to=f"2026-06-{12+i}")
    assert len(client._request_times) == 3
    with patch("app.services.api_football.time.sleep") as mock_sleep:
        client.get_fixtures(date_from="2026-06-20", date_to="2026-06-21")
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 0 < sleep_time <= 60.05


def test_daily_budget_blocks_requests():
    """日配额用尽后抛 RateLimitedError."""
    client = _mock_client([(200, [{"id": i}]) for i in range(5)], daily_limit=2)
    client.get_fixtures(date_from="2026-06-11", date_to="2026-06-12")
    client.get_fixtures(date_from="2026-06-13", date_to="2026-06-14")
    with pytest.raises(RateLimitedError) as exc:
        client.get_fixtures(date_from="2026-06-15", date_to="2026-06-16")
    assert "日配额" in str(exc.value)


def test_401_returns_apikey_missing():
    """服务端 401 → ApiKeyMissingError."""

    def handler(request):
        return httpx.Response(401, json={"message": "Invalid key"})

    client = ApiFootballClient(api_key="bad", _transport=httpx.MockTransport(handler))
    with pytest.raises(ApiKeyMissingError) as exc:
        client.get_fixtures()
    assert "401" in str(exc.value)


def test_429_returns_rate_limited():
    """服务端 429 → RateLimitedError."""

    def handler(request):
        return httpx.Response(429, json={"message": "Too many requests"})

    client = ApiFootballClient(api_key="test", _transport=httpx.MockTransport(handler))
    with pytest.raises(RateLimitedError) as exc:
        client.get_fixtures()
    assert "429" in str(exc.value)


def test_500_returns_http_error():
    """服务端 500 → ApiFootballHttpError."""

    def handler(request):
        return httpx.Response(500, json={"message": "Internal error"})

    client = ApiFootballClient(api_key="test", _transport=httpx.MockTransport(handler))
    with pytest.raises(ApiFootballHttpError) as exc:
        client.get_fixtures()
    assert "500" in str(exc.value)


def test_network_error_returns_http_error():
    """网络异常 → ApiFootballHttpError."""

    def handler(request):
        raise httpx.ConnectError("simulated network failure")

    client = ApiFootballClient(api_key="test", _transport=httpx.MockTransport(handler))
    with pytest.raises(ApiFootballHttpError) as exc:
        client.get_fixtures()
    assert "请求失败" in str(exc.value)


def test_get_fixtures_unwraps_response():
    """get_fixtures 返回 response 列表."""
    client = _mock_client([(200, [{"fixture": {"id": 1}}])])
    result = client.get_fixtures(date_from="2026-06-11", date_to="2026-06-12")
    assert result == [{"fixture": {"id": 1}}]


def test_get_live_fixtures_passes_live_param():
    """get_live_fixtures 传递 live=all."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"response": [{"fixture": {"id": 1}}], "errors": []})

    client = ApiFootballClient(api_key="test", _transport=httpx.MockTransport(handler))
    result = client.get_live_fixtures()
    assert result == [{"fixture": {"id": 1}}]
    assert captured["params"].get("live") == "all"


def test_get_standings_and_events():
    """standings/events 端点可用."""
    client = _mock_client([(200, [{"league": {"standings": []}}]), (200, [{"type": "Goal"}])])
    standings = client.get_standings()
    assert standings == [{"league": {"standings": []}}]
    events = client.get_events(123)
    assert events == [{"type": "Goal"}]
    assert client._test_call_count["n"] == 2


def test_remaining_daily():
    """remaining_daily 返回正确剩余数."""
    client = _mock_client([(200, [{"id": 1}])], daily_limit=5)
    assert client.remaining_daily() == 5
    client.get_fixtures(date_from="2026-06-11", date_to="2026-06-12")
    assert client.remaining_daily() == 4


def test_context_manager_closes_client():
    """with 语法自动 close."""
    handler, _ = _make_handler([(200, [{"id": 1}])])
    with ApiFootballClient(
        api_key="test", _transport=httpx.MockTransport(handler)
    ) as client:
        client.get_fixtures()
    assert client._client.is_closed


def test_team_name_aliases():
    """队名别名映射正确."""
    assert fifa_code_from_team_name("South Korea") == "KOR"
    assert fifa_code_from_team_name("USA") == "USA"
    assert fifa_code_from_team_name("Côte d'Ivoire") == "CIV"
    assert normalize_team_name("  ARGENTINA  ") == "argentina"
