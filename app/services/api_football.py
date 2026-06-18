"""API-Football 客户端（v0.14.0）.

免费层约束（2026-06）:
- 100 requests / 天（UTC 00:00 重置）
- 10 requests / 分钟（硬上限）
- 世界杯数据端点: league=1, season=2026
- 认证头: x-apisports-key（直接调用 api-sports.io）

设计要点:
1. 滑动窗口限速 + 日预算守护,超配额时抛出 RateLimitedError,供上层 fallback.
2. 内存缓存 15min,避免重复请求.
3. 同步 httpx.Client,与项目其他服务一致.
4. 支持 httpx.MockTransport 注入,便于测试.
5. 仅返回原始 response 列表,不做 ORM 映射.

注册: https://www.api-football.com/ 或 RapidAPI 搜索 API-Football.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import httpx


class ApiFootballError(Exception):
    """API-Football 错误基类."""


class ApiKeyMissingError(ApiFootballError):
    """未配置 API Key."""


class RateLimitedError(ApiFootballError):
    """触发速率限制（分钟或日配额）."""


class ApiFootballHttpError(ApiFootballError):
    """其他 HTTP/网络错误."""


# 常见队名/TLS → FIFA 3-letter code 别名
# TLA 多数已与 FIFA code 一致,此处仅列出差异或特殊写法
_NAME_TO_FIFA_ALIASES: Dict[str, str] = {
    "south korea": "KOR",
    "korea republic": "KOR",
    "korea": "KOR",
    "united states": "USA",
    "usa": "USA",
    "bosnia and herzegovina": "BIH",
    "bosnia & herzegovina": "BIH",
    "ivory coast": "CIV",
    "cote d'ivoire": "CIV",
    "côte d'ivoire": "CIV",
    "cape verde": "CPV",
    "cape verde islands": "CPV",
    "curaçao": "CUW",
    "curacao": "CUW",
    "dr congo": "COD",
    "democratic republic of the congo": "COD",
    "congo dr": "COD",
    "czech republic": "CZE",
    "czechia": "CZE",
    "england": "ENG",
    "scotland": "SCO",
    "wales": "WAL",
    "northern ireland": "NIR",
    "uruguay": "URU",
    "paraguay": "PAR",
    "ecuador": "ECU",
    "peru": "PER",
    "chile": "CHI",
    "venezuela": "VEN",
    "bolivia": "BOL",
    "argentina": "ARG",
    "brazil": "BRA",
    "germany": "GER",
    "france": "FRA",
    "spain": "ESP",
    "portugal": "POR",
    "netherlands": "NED",
    "belgium": "BEL",
    "switzerland": "SUI",
    "croatia": "CRO",
    "serbia": "SRB",
    "denmark": "DEN",
    "sweden": "SWE",
    "poland": "POL",
    "ukraine": "UKR",
    "turkey": "TUR",
    "morocco": "MAR",
    "senegal": "SEN",
    "tunisia": "TUN",
    "cameroon": "CMR",
    "ghana": "GHA",
    "nigeria": "NGA",
    "egypt": "EGY",
    "algeria": "ALG",
    "iran": "IRN",
    "japan": "JPN",
    "australia": "AUS",
    "qatar": "QAT",
    "saudi arabia": "KSA",
    "iraq": "IRQ",
    "uzbekistan": "UZB",
    "jordan": "JOR",
    "canada": "CAN",
    "mexico": "MEX",
    "panama": "PAN",
    "costa rica": "CRC",
    "jamaica": "JAM",
    "honduras": "HON",
    "guatemala": "GUA",
    "new zealand": "NZL",
}


def normalize_team_name(name: Optional[str]) -> str:
    """统一队名：小写、去首尾空格、压缩连续空格."""
    if not name:
        return ""
    return " ".join(name.strip().lower().split())


def fifa_code_from_team_name(name: Optional[str]) -> Optional[str]:
    """从队名解析 FIFA code，支持别名."""
    norm = normalize_team_name(name)
    if not norm:
        return None
    # 直接命中别名表
    if norm in _NAME_TO_FIFA_ALIASES:
        return _NAME_TO_FIFA_ALIASES[norm]
    # 取每个单词首字母大写拼接（简单启发式）
    parts = norm.split()
    if parts:
        return "".join(p[0].upper() for p in parts if p)
    return None


class ApiFootballClient:
    """API-Football v3 客户端."""

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(
        self,
        api_key: str = "",
        host: str = "v3.football.api-sports.io",
        rate_limit_per_min: int = 10,
        daily_limit: int = 100,
        cache_ttl_seconds: int = 900,
        timeout_seconds: int = 20,
        _transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """初始化客户端.

        Args:
            api_key: API-Football key（x-apisports-key）。
            host: API host，直接调用默认 api-sports.io；RapidAPI 可改。
            rate_limit_per_min: 每分钟最大请求数。
            daily_limit: 每日最大请求数（UTC 00:00 重置）。
            cache_ttl_seconds: 内存缓存 TTL。
            timeout_seconds: 单次请求超时。
            _transport: httpx transport，仅测试用。
        """
        self.api_key = api_key
        self.host = host
        self.rate_limit_per_min = rate_limit_per_min
        self.daily_limit = daily_limit
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._request_times: Deque[float] = deque()
        self._daily_requests = 0
        self._last_reset_date = datetime.now(timezone.utc).date()
        base_url = f"https://{host}"
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"x-apisports-key": api_key},
            transport=_transport,
        )

    def __enter__(self) -> "ApiFootballClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        """关闭底层 httpx.Client."""
        self._client.close()

    def _check_api_key(self) -> None:
        """无 key 时直接抛错，不消耗配额."""
        if not self.api_key:
            raise ApiKeyMissingError(
                "API_FOOTBALL_KEY 未配置。"
                "请到 https://www.api-football.com/ 注册免费 key，"
                "在 .env 填入 API_FOOTBALL_KEY=<your_key>"
            )

    def _reset_daily_if_needed(self) -> None:
        """UTC 日期变化时重置日计数."""
        today = datetime.now(timezone.utc).date()
        if today != self._last_reset_date:
            self._daily_requests = 0
            self._last_reset_date = today

    def _check_daily_budget(self) -> None:
        """检查日配额；超配额抛 RateLimitedError."""
        self._reset_daily_if_needed()
        if self.daily_limit > 0 and self._daily_requests >= self.daily_limit:
            raise RateLimitedError(
                f"API-Football 日配额已用尽: {self._daily_requests}/{self.daily_limit}"
            )

    def _wait_for_rate_limit(self) -> None:
        """滑动窗口限速：超过 rate_limit_per_min 时 sleep 至最早请求过期."""
        if len(self._request_times) < self.rate_limit_per_min:
            return
        now = time.monotonic()
        oldest = self._request_times[0]
        elapsed = now - oldest
        if elapsed < 60:
            sleep_time = 60 - elapsed + 0.05
            time.sleep(sleep_time)

    def _record_request(self) -> None:
        """记录一次请求时间戳，并清理 60s 外旧记录."""
        self._reset_daily_if_needed()
        now = time.monotonic()
        self._request_times.append(now)
        self._daily_requests += 1
        cutoff = now - 60
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()

    def _cache_key(self, path: str, params: Optional[Dict]) -> str:
        """构造缓存 key（params 排序后拼接）."""
        if not params:
            return path
        items = sorted(params.items())
        return f"{path}?{items}"

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """带限速、缓存、日预算的 GET.

        Returns:
            API 返回 JSON 的 "response" 字段（通常是 list）。
        Raises:
            ApiKeyMissingError: 未配置 key 或服务端 401。
            RateLimitedError: 触发 429 或日配额用尽。
            ApiFootballHttpError: 其他 HTTP/网络错误。
        """
        self._check_api_key()
        self._check_daily_budget()

        cache_key = self._cache_key(path, params)
        now = time.time()
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self.cache_ttl_seconds:
                return data

        self._wait_for_rate_limit()
        try:
            resp = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ApiFootballHttpError(f"API-Football 请求失败: {exc}") from exc

        # 错误分类
        if resp.status_code == 401:
            raise ApiKeyMissingError(
                f"API-Football 返回 401(API key 无效): {resp.text[:200]}"
            )
        if resp.status_code == 429:
            raise RateLimitedError(
                f"API-Football 返回 429(超过速率限制): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise ApiFootballHttpError(
                f"API-Football HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except Exception as exc:
            raise ApiFootballHttpError(f"API-Football 返回非 JSON: {exc}") from exc

        # API-Football 标准响应结构 {"response": [...], "errors": []}
        data = payload.get("response", payload)
        self._record_request()
        self._cache[cache_key] = (now, data)
        return data

    def clear_cache(self) -> None:
        """清空缓存和请求时间记录."""
        self._cache.clear()
        self._request_times.clear()

    def remaining_daily(self) -> int:
        """返回当日剩余配额."""
        self._reset_daily_if_needed()
        return max(0, self.daily_limit - self._daily_requests)

    # ==================== 业务端点 ====================

    def get_teams(self, league_id: int = 1, season: int = 2026) -> List[Dict]:
        """获取指定联赛/赛季球队列表."""
        return self._get(
            "/teams",
            {"league": league_id, "season": season},
        ) or []

    def get_fixtures(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        league_id: int = 1,
        season: int = 2026,
        live: bool = False,
    ) -> List[Dict]:
        """获取比赛列表.

        Args:
            date_from: ISO 日期,如 "2026-06-11"。
            date_to: ISO 日期。
            league_id: 联赛 ID,世界杯默认 1。
            season: 赛季,默认 2026。
            live: 是否仅取进行中的比赛（会忽略 date_from/date_to）。
        """
        params: Dict[str, Any] = {"league": league_id, "season": season}
        if live:
            params["live"] = "all"
        else:
            if date_from:
                params["dateFrom"] = date_from
            if date_to:
                params["dateTo"] = date_to
        return self._get("/fixtures", params) or []

    def get_live_fixtures(
        self, league_id: int = 1, season: int = 2026
    ) -> List[Dict]:
        """快捷方法：仅取进行中的比赛."""
        return self.get_fixtures(league_id=league_id, season=season, live=True)

    def get_standings(
        self, league_id: int = 1, season: int = 2026
    ) -> List[Dict]:
        """获取积分榜.

        通常返回一个元素，结构包含 league + standings 数组。
        """
        return self._get(
            "/standings",
            {"league": league_id, "season": season},
        ) or []

    def get_events(self, fixture_id: int) -> List[Dict]:
        """获取单场比赛事件（进球/红黄牌/换人）."""
        return self._get("/fixtures/events", {"fixture": fixture_id}) or []
