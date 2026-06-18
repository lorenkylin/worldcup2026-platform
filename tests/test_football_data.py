"""football_data 客户端单元测试（v0.5.1）.

用 httpx.MockTransport 注入 mock handler,验证:
- 限速 + 缓存 + 错误分类
- 不实际访问 football-data.co

覆盖:
  - 无 api_key → ApiKeyMissingError
  - 缓存命中 / 缓存过期重取
  - 10 req/min 滑动窗口触发 sleep
  - 401 / 429 / 500 错误分类
  - /matches 端点自动 unwrap "matches" 键
  - 上下文管理器自动 close
  - 不同 params 缓存隔离
"""
import time
from unittest.mock import patch

import httpx
import pytest

from app.services.football_data import (
    ApiKeyMissingError,
    FootballDataClient,
    FootballDataHttpError,
    RateLimitedError,
)


# ============ 测试辅助 ============

def _make_handler(responses):
    """构造 httpx.MockTransport 的 handler.

    Args:
        responses: list[(status, body)],handler 按调用顺序消费.
    """
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        if idx >= len(responses):
            # 未配置的请求 → 返回 404 + 错误信息
            return httpx.Response(404, json={"error": "no more mock responses"})
        status, body = responses[idx]
        return httpx.Response(status, json=body)

    return handler, call_count


def _mock_client(responses, **kwargs) -> FootballDataClient:
    """构造带 mock transport 的客户端."""
    handler, call_count = _make_handler(responses)
    kwargs.setdefault("api_key", "test_token")
    kwargs.setdefault("cache_ttl_seconds", 60)  # 短 TTL 便于测试
    client = FootballDataClient(_transport=httpx.MockTransport(handler), **kwargs)
    client._test_call_count = call_count  # 注入测试计数器
    return client


# ============ ApiKeyMissingError ============

def test_no_api_key_raises_immediately():
    """无 api_key 时 _get 直接抛错,不消耗限速配额."""
    client = FootballDataClient(api_key="")
    with pytest.raises(ApiKeyMissingError) as exc:
        client._get("/matches")
    assert "未配置" in str(exc.value)
    assert len(client._request_times) == 0  # 没发请求


# ============ 缓存 ============

def test_cache_hit_within_ttl():
    """缓存命中:第二次调用不发请求."""
    client = _mock_client([(200, {"matches": [{"id": 1}]})])
    a = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    b = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert a == b == [{"id": 1}]
    assert client._test_call_count["n"] == 1  # 只请求一次


@pytest.mark.slow
def test_cache_expired_refetches():
    """缓存过期后重新请求."""
    client = _mock_client(
        [
            (200, {"matches": [{"id": 1}]}),
            (200, {"matches": [{"id": 2}]}),
        ],
        cache_ttl_seconds=1,
    )
    a = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert a == [{"id": 1}]
    time.sleep(1.1)  # 等 TTL 过期
    b = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert b == [{"id": 2}]
    assert client._test_call_count["n"] == 2


def test_different_params_different_cache_keys():
    """不同 params 缓存隔离."""
    client = _mock_client(
        [
            (200, {"matches": [{"id": 1}]}),
            (200, {"matches": [{"id": 2}]}),
        ]
    )
    a = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    b = client.get_matches_by_date_range("2026-06-22", "2026-06-28")
    assert a == [{"id": 1}]
    assert b == [{"id": 2}]
    assert client._test_call_count["n"] == 2


# ============ 限速 ============

def test_rate_limit_triggers_sleep():
    """超过 rate_limit_per_min 时 sleep 至最早请求过期."""
    # rate=3 便于测试,3 次请求后第 4 次必须 sleep
    # 用不同日期范围强制 cache miss,确保每次都发请求
    client = _mock_client(
        [(200, {"matches": [{"id": i}]}) for i in range(10)],
        rate_limit_per_min=3,
    )
    # 前 3 次不需要 sleep(用不同日期避开缓存)
    for i in range(3):
        client.get_matches_by_date_range(f"2026-06-{15+i}", f"2026-06-{21+i}")
    assert len(client._request_times) == 3
    # 第 4 次应触发 sleep,monkey-patch time.sleep 验证
    with patch("app.services.football_data.time.sleep") as mock_sleep:
        client.get_matches_by_date_range("2026-06-30", "2026-07-06")
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 0 < sleep_time <= 60.05  # 留 50ms 缓冲


def test_rate_limit_window_cleanup():
    """60s 外的旧请求时间戳被清理."""
    client = FootballDataClient(api_key="test", cache_ttl_seconds=60)
    # 手动注入 5 个时间戳,2 个在 60s 外
    base = time.monotonic() - 70
    for i in range(5):
        client._request_times.append(base + i * 0.1)  # 跨 0.4s
    assert len(client._request_times) == 5
    # 触发一次 _record_request,清理旧记录
    client._record_request()
    # 旧记录(70s 外)被清,剩下较新的(60s 内)
    assert len(client._request_times) < 5


# ============ 错误分类 ============

def test_401_returns_apikey_missing():
    """服务端 401 → ApiKeyMissingError."""
    client = _mock_client([(401, {"message": "Invalid token"})])
    with pytest.raises(ApiKeyMissingError) as exc:
        client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert "401" in str(exc.value)


def test_429_returns_rate_limited():
    """服务端 429 → RateLimitedError."""
    client = _mock_client([(429, {"message": "Too many requests"})])
    with pytest.raises(RateLimitedError) as exc:
        client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert "10 req/min" in str(exc.value)


def test_500_returns_http_error():
    """服务端 500 → FootballDataHttpError."""
    client = _mock_client([(500, {"message": "Internal error"})])
    with pytest.raises(FootballDataHttpError) as exc:
        client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert "500" in str(exc.value)


def test_network_error_returns_http_error():
    """网络异常 → FootballDataHttpError."""
    def handler(request):
        raise httpx.ConnectError("simulated network failure")

    client = FootballDataClient(
        api_key="test", _transport=httpx.MockTransport(handler), cache_ttl_seconds=60
    )
    with pytest.raises(FootballDataHttpError) as exc:
        client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert "请求失败" in str(exc.value)


# ============ 端点 unwrap ============

def test_get_matches_unwraps_matches_key():
    """/matches 端点返回 dict → 自动 unwrap "matches" 列表."""
    client = _mock_client(
        [
            (
                200,
                {
                    "matches": [
                        {"id": 1, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}},
                        {"id": 2, "homeTeam": {"name": "C"}, "awayTeam": {"name": "D"}},
                    ],
                    "count": 2,
                },
            )
        ]
    )
    result = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert len(result) == 2
    assert result[0]["homeTeam"]["name"] == "A"


def test_get_matches_passes_through_list():
    """/matches 直接返回 list 也兼容."""
    client = _mock_client([(200, [{"id": 1}, {"id": 2}])])
    result = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert result == [{"id": 1}, {"id": 2}]


def test_get_team_returns_dict():
    """/teams/{id} 直接返回 dict(不 unwrap)."""
    client = _mock_client(
        [
            (
                200,
                {"id": 789, "name": "Brazil", "tla": "BRA", "founded": 1914},
            )
        ]
    )
    team = client.get_team(789)
    assert team["name"] == "Brazil"


def test_get_competition_standings_returns_dict():
    """/competitions/{id}/standings 返回 dict 含 "standings" 键."""
    client = _mock_client(
        [
            (
                200,
                {
                    "competition": {"name": "WC"},
                    "standings": [{"table": []}],
                },
            )
        ]
    )
    result = client.get_competition_standings("WC")
    assert result["competition"]["name"] == "WC"


# ============ 测试辅助方法 ============

def test_clear_cache():
    """clear_cache 同时清缓存和请求时间记录."""
    client = _mock_client([(200, {"matches": [{"id": 1}]})])
    client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    assert len(client._cache) == 1
    assert len(client._request_times) == 1
    client.clear_cache()
    assert len(client._cache) == 0
    assert len(client._request_times) == 0


def test_context_manager_closes_client():
    """with 语法自动 close."""
    handler, _ = _make_handler([(200, {"matches": []})])
    with FootballDataClient(
        api_key="test", _transport=httpx.MockTransport(handler)
    ) as client:
        client.get_matches_by_date_range("2026-06-15", "2026-06-21")
    # close() 后 httpx.Client 应被关闭 → 再请求会报错
    # 不强验证 transport,只验证 close() 被调用
    assert client._client.is_closed


def test_cache_key_sorts_params():
    """同内容不同顺序的 params 命中同一缓存."""
    client = _mock_client([(200, {"matches": [{"id": 1}]})])
    # 两次请求 param 顺序不同,但内容相同
    client._get("/matches", {"dateFrom": "2026-06-15", "dateTo": "2026-06-21"})
    # 此时 _cache 已有 1 个键
    assert len(client._cache) == 1
    # 用字典反转顺序(实际 Python 3.7+ dict 保序,但 sorted 应一致)
    client._get("/matches", {"dateTo": "2026-06-21", "dateFrom": "2026-06-15"})
    # 还是 1 个键(缓存命中)
    assert len(client._cache) == 1
