"""football-data.co v4 API 客户端（v0.5.1 元数据接入）.

免费层约束（实测）:
- 必须带 X-Auth-Token header（注册邮箱即可，无付费）
- 10 req/min 速率限制（硬上限）
- 无赔率端点（只有比赛/球队/积分）
- 数据用途:作为 wc26 主源的交叉验证 + 元数据补全

设计要点:
1. 滑动窗口限速:Deque 记录请求时间戳，60s 窗口最多 10 个
2. 内存缓存:dict[path+params] = (timestamp, data)，15min TTL
3. 同步调用:httpx.Client（与项目其他服务一致）
4. 异常分类:ApiKeyMissingError(401) / RateLimitedError(429) / FootballDataHttpError(其他)
5. transport 注入便于单元测试 mock httpx

注册 token: https://www.football-data.org/  →  邮件激活  →  控制台取 token
配置: .env 加 FOOTBALL_DATA_API_KEY=<your_token> + FOOTBALL_DATA_ENABLED=true
"""

import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

import httpx


class FootballDataError(Exception):
    """football-data.co API 错误基类."""


class ApiKeyMissingError(FootballDataError):
    """未配置 API Key（主人未填 FOOTBALL_DATA_API_KEY）."""


class RateLimitedError(FootballDataError):
    """超过 10 req/min 限制（理论不应触发，本客户端已内置滑动窗口）."""


class FootballDataHttpError(FootballDataError):
    """其他 HTTP 错误（5xx / 网络异常 / 4xx 非 401/429）."""


class FootballDataClient:
    """football-data.co v4 API 同步客户端.

    用法:
        client = FootballDataClient(api_key="<token>")
        matches = client.get_matches_by_date_range("2026-06-15", "2026-06-21")
        team = client.get_team(789)  # 巴西 ID

    测试用法:
        client = FootballDataClient(api_key="test", _transport=httpx.MockTransport(handler))
    """

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(
        self,
        api_key: str = "",
        rate_limit_per_min: int = 10,
        cache_ttl_seconds: int = 900,
        timeout_seconds: int = 20,
        _transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """初始化客户端.

        Args:
            api_key: X-Auth-Token 值（免费 token 即可）。
            rate_limit_per_min: 每分钟最大请求数（默认 10，免费层硬上限）。
            cache_ttl_seconds: 缓存 TTL（默认 900s = 15min）。
            timeout_seconds: 单次请求超时。
            _transport: httpx transport（仅测试用 mock，生产传 None）。
        """
        self.api_key = api_key
        self.rate_limit_per_min = rate_limit_per_min
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._request_times: Deque[float] = deque()
        # httpx.Client 接受 transport(便于测试 mock);无 key 时不带 header
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=timeout_seconds,
            headers={"X-Auth-Token": api_key} if api_key else {},
            transport=_transport,
        )

    def _check_api_key(self) -> None:
        """无 key 时直接抛错,避免无效请求浪费限速配额."""
        if not self.api_key:
            raise ApiKeyMissingError(
                "FOOTBALL_DATA_API_KEY 未配置. "
                "请到 https://www.football-data.org/ 注册免费 token, "
                "在 .env 填入 FOOTBALL_DATA_API_KEY=<your_token>"
            )

    def _wait_for_rate_limit(self) -> None:
        """滑动窗口限速:超过 rate_limit_per_min 时 sleep 至最早请求过期 60s."""
        if len(self._request_times) < self.rate_limit_per_min:
            return
        now = time.monotonic()
        oldest = self._request_times[0]
        elapsed = now - oldest
        if elapsed < 60:
            sleep_time = 60 - elapsed + 0.05  # 留 50ms 缓冲避免边界 race
            time.sleep(sleep_time)

    def _record_request(self) -> None:
        """记录一次请求时间戳,并清理 60s 外的旧记录."""
        now = time.monotonic()
        self._request_times.append(now)
        cutoff = now - 60
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()

    def _cache_key(self, path: str, params: Optional[Dict]) -> str:
        """构造缓存 key(path + 排序后的 params,避免不同参数命中同一缓存)."""
        if not params:
            return path
        # 用 sorted 保证 {a:1,b:2} 和 {b:2,a:1} 同一 key
        items = sorted(params.items())
        return f"{path}?{items}"

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """带限速 + 缓存的 GET.

        Args:
            path: API 路径,如 "/matches".
            params: 查询参数.

        Returns:
            解析后的 JSON 响应(dict 或 list).

        Raises:
            ApiKeyMissingError: 未配置 api_key 或服务端返回 401.
            RateLimitedError: 服务端返回 429.
            FootballDataHttpError: 其他 HTTP 错误.
        """
        self._check_api_key()
        cache_key = self._cache_key(path, params)
        now = time.time()
        # 缓存命中检查
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self.cache_ttl_seconds:
                return data  # 缓存命中,不消耗限速配额

        self._wait_for_rate_limit()
        try:
            resp = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise FootballDataHttpError(f"football-data.co 请求失败: {exc}") from exc

        # 错误分类
        if resp.status_code == 401:
            raise ApiKeyMissingError(
                f"football-data.co 返回 401(API key 无效或过期): {resp.text[:200]}"
            )
        if resp.status_code == 429:
            raise RateLimitedError(
                "football-data.co 返回 429(超过 10 req/min). "
                "本客户端已内置限速,出现此错误说明有其他客户端并发."
            )
        if resp.status_code >= 400:
            raise FootballDataHttpError(
                f"football-data.co HTTP {resp.status_code}: {resp.text[:200]}"
            )

        self._record_request()
        data = resp.json()
        self._cache[cache_key] = (now, data)
        return data

    # ============== 公开 API 端点 ==============

    def get_matches_by_date_range(self, date_from: str, date_to: str) -> list:
        """日期范围获取比赛列表.

        Args:
            date_from: ISO 8601 起始日期(YYYY-MM-DD).
            date_to: ISO 8601 结束日期(YYYY-MM-DD).

        Returns:
            matches list(dict),每个 dict 含 id/homeTeam/awayTeam/status/utcDate/score 等字段.
        """
        # football-data v4 返回 dict,真实列表在 "matches" 键
        resp = self._get("/matches", {"dateFrom": date_from, "dateTo": date_to})
        if isinstance(resp, dict) and "matches" in resp:
            return resp["matches"]
        return resp if isinstance(resp, list) else []

    def get_team(self, team_id: int) -> dict:
        """获取球队详情(id 由 competition/teams 端点返回)."""
        return self._get(f"/teams/{team_id}")

    def get_competition_standings(self, competition_id: str) -> dict:
        """获取某赛事积分榜(competition_id 形如 'WC' = 世界杯)."""
        return self._get(f"/competitions/{competition_id}/standings")

    def get_competitions(self) -> list:
        """获取赛事列表(用于查找 WC 的 id)."""
        resp = self._get("/competitions")
        if isinstance(resp, dict) and "competitions" in resp:
            return resp["competitions"]
        return resp if isinstance(resp, list) else []

    # ============== 测试辅助 ==============

    def clear_cache(self) -> None:
        """清空缓存和请求时间记录(测试用)."""
        self._cache.clear()
        self._request_times.clear()

    def close(self) -> None:
        """关闭 httpx 连接(测试/上下文退出)."""
        self._client.close()

    def __enter__(self) -> "FootballDataClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
