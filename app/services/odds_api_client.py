"""v0.7.2 赔率 API 客户端.

设计原则:
- **零预算路线**: 仅在主人提供 ODDS_API_KEY 时调用真实 API;否则用 mock 生成合理赔率
- **接口统一**: 不论真 mock,都返回相同 dict 结构,upsert_to_match_odds() 直接用
- **滑动窗口限速**: 防止真实 API 免费层被封(30 req/min)
- **失败 fallback**: 任一 API 失败自动降级 mock,绝不阻塞主流程

支持的 source:
- `mock`: 在客户端生成"合理赔率",基于 Elo 评分计算赔率 + 5% 利润 + 微随机扰动
  仅供开发/演示,生产环境务必配置真实 API key
- `the_odds_api`: The Odds API (https://the-odds-api.com/) 免费层 500 req/月
- `pinnacle`: Pinnacle Sports (付费),占位未实现
"""
from __future__ import annotations

import logging
import random
import re
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Match, OddsSnapshot, PredictionLog, Team
from app.services.odds_service import aggregate_multi_bookmaker

logger = logging.getLogger(__name__)


# The Odds API 队名 → FIFA code 常见别名(与 DB name_en 有差异时兜底)
_ODDS_API_TEAM_ALIASES: Dict[str, str] = {
    "south korea": "KOR",
    "korea republic": "KOR",
    "united states": "USA",
    "usa": "USA",
    "bosnia and herzegovina": "BIH",
    "bosnia & herzegovina": "BIH",
    "ivory coast": "CIV",
    "cote d'ivoire": "CIV",
    "cape verde": "CPV",
    "cape verde islands": "CPV",
    "curaçao": "CUW",
    "curacao": "CUW",
    "dr congo": "COD",
    "democratic republic of the congo": "COD",
    "haiti": "HAI",
    "jordan": "JOR",
    "saudi arabia": "KSA",
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
    "norway": "NOR",
    "poland": "POL",
    "ukraine": "UKR",
    "turkey": "TUR",
    "austria": "AUT",
    "hungary": "HUN",
    "romania": "ROU",
    "slovakia": "SVK",
    "slovenia": "SVN",
    "russia": "RUS",
    "greece": "GRE",
    "israel": "ISR",
    "egypt": "EGY",
    "morocco": "MAR",
    "nigeria": "NGA",
    "senegal": "SEN",
    "tunisia": "TUN",
    "algeria": "ALG",
    "cameroon": "CMR",
    "ghana": "GHA",
    "mali": "MLI",
    "burkina faso": "BFA",
    "south africa": "RSA",
    "new zealand": "NZL",
    "australia": "AUS",
    "japan": "JPN",
    "iran": "IRN",
    "iraq": "IRQ",
    "uzbekistan": "UZB",
    "qatar": "QAT",
    "canada": "CAN",
    "mexico": "MEX",
    "panama": "PAN",
    "honduras": "HON",
    "costa rica": "CRC",
    "jamaica": "JAM",
    "guatemala": "GUA",
    "el salvador": "SLV",
    "nicaragua": "NCA",
    "dominican republic": "DOM",
    "cuba": "CUB",
}


# === 滑动窗口限速 ===
class _SlidingWindowRateLimiter:
    """滑动窗口限速器(线程安全,deque 实现).

    用于 The Odds API 免费层:30 req/min.
    """

    def __init__(self, max_calls: int, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._call_times: deque = deque()

    def wait_if_needed(self) -> None:
        """若窗口内已满,等待最早调用过期."""
        now = time.monotonic()
        # 清理窗口外的记录
        while self._call_times and (now - self._call_times[0]) > self.window_seconds:
            self._call_times.popleft()
        # 窗口内已达上限,等最早过期
        if len(self._call_times) >= self.max_calls:
            sleep_for = self.window_seconds - (now - self._call_times[0])
            if sleep_for > 0:
                logger.info(
                    "[odds_api] rate limit reached, sleeping %.2fs", sleep_for
                )
                time.sleep(sleep_for)
        self._call_times.append(time.monotonic())


_rate_limiter = _SlidingWindowRateLimiter(
    max_calls=settings.odds_api_rate_limit_per_min,
    window_seconds=60,
)


def _elo_to_decimal_odds(
    home_elo: int,
    away_elo: int,
    margin: float = 0.05,
    noise: float = 0.02,
) -> Dict[str, float]:
    """基于 Elo 评分 + 平局概率模型生成 1X2 赔率(mock 用).

    模型:
      home_p = 1 / (1 + 10^((away - home + home_bonus) / 400))
      draw_p = 0.28 (固定)
      away_p = 1 - home_p - draw_p
      加 5% 博彩公司利润 + 微随机扰动

    Returns:
        {"home_win": decimal, "draw": decimal, "away_win": decimal}
    """
    home_bonus = 50  # 主队加分
    diff = (home_elo + home_bonus) - away_elo
    home_p = 1.0 / (1.0 + 10 ** (-diff / 400))
    draw_p = 0.28
    away_p = max(0.0, 1.0 - home_p - draw_p)

    # 加 margin 和 noise
    home_p = max(0.02, min(0.95, home_p * (1 - margin) + random.uniform(-noise, noise)))
    away_p = max(0.02, min(0.95, away_p * (1 - margin) + random.uniform(-noise, noise)))
    draw_p = max(0.05, 1.0 - home_p - away_p - margin * 0.5)

    return {
        "home_win": round(1.0 / home_p, 2),
        "draw": round(1.0 / draw_p, 2),
        "away_win": round(1.0 / away_p, 2),
    }


# === 缓存 ===
_cache: Dict[str, tuple] = {}  # (cache_key) -> (expires_at, payload)


def _cache_get(key: str) -> Optional[List[Dict]]:
    """读内存缓存."""
    if key not in _cache:
        return None
    expires_at, payload = _cache[key]
    if time.time() < expires_at:
        return payload
    del _cache[key]
    return None


def _cache_set(key: str, payload: List[Dict], ttl: int) -> None:
    _cache[key] = (time.time() + ttl, payload)


# === Mock 数据源 ===
def _fetch_mock(db: Session, target_dates: List[str]) -> List[Dict]:
    """Mock 赔率生成器:基于 DB 中未完赛比赛 + Elo 评分生成合理赔率.

    Args:
        target_dates: ["2026-06-11", "2026-06-12", ...] ISO date list(北京时间)
    Returns:
        [{match_id, bookmaker, home_win, draw, away_win, over_2_5, under_2_5, source, fetched_at}, ...]
    """
    from zoneinfo import ZoneInfo

    display_tz = ZoneInfo(settings.display_timezone)
    target_dt = [datetime.fromisoformat(d).date() for d in target_dates]

    matches = (
        db.query(Match)
        .filter(Match.status.in_(["scheduled", "live"]))
        .all()
    )

    result: List[Dict] = []
    fetched_at = datetime.now(timezone.utc)

    for m in matches:
        if not m.kickoff_at:
            continue
        # 统一按北京时间(展示时区)过滤,与前端/admin 语义一致
        beijing = m.kickoff_at.replace(tzinfo=timezone.utc).astimezone(display_tz)
        if beijing.date() not in target_dt:
            continue

        home_elo = m.home_team.elo_rating if m.home_team and m.home_team.elo_rating else 1500
        away_elo = m.away_team.elo_rating if m.away_team and m.away_team.elo_rating else 1500

        odds_1x2 = _elo_to_decimal_odds(home_elo, away_elo)

        # 大小球用全场预期进球 2.7 估算
        # over_2_5 ≈ 1/1.95, under_2_5 ≈ 1/2.05(略偏 over)
        result.append({
            "match_id": m.id,
            "bookmaker": settings.odds_default_bookmaker,
            "home_win": odds_1x2["home_win"],
            "draw": odds_1x2["draw"],
            "away_win": odds_1x2["away_win"],
            "over_2_5": 1.95,
            "under_2_5": 2.05,
            "source": "mock",
            "fetched_at": fetched_at,
        })

    return result


def _normalize_team_name(name: Optional[str]) -> str:
    """统一队名用于查找：小写、去首尾空格、压缩连续空格."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().lower())


# === The Odds API ===
def _fetch_the_odds_api(db: Session, target_dates: List[str]) -> List[Dict]:
    """The Odds API 客户端：解析响应并映射到 Match.id.

    API 文档: https://the-odds-api.com/liveapi/guides/v4/
    端点: GET /v4/sports/soccer/odds/?regions=uk&markets=h2h,totals&oddsFormat=decimal
    """
    if not settings.odds_api_key:
        logger.warning("[odds_api] ODDS_API_KEY 未配置,降级 mock")
        return []

    _rate_limiter.wait_if_needed()

    url = f"{settings.odds_api_base_url}/sports/soccer/odds/"
    params = {
        "regions": "uk",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
        "apiKey": settings.odds_api_key,
    }
    try:
        with httpx.Client(timeout=settings.odds_api_timeout_seconds) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            events = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.error("[odds_api] The Odds API 调用失败: %s", e)
        return []

    # 队名查找表
    teams = db.query(Team).all()
    name_to_code: Dict[str, str] = {}
    for t in teams:
        name_to_code[_normalize_team_name(t.name_en)] = t.fifa_code
        name_to_code[_normalize_team_name(t.name_zh)] = t.fifa_code
    name_to_code.update({k: v for k, v in _ODDS_API_TEAM_ALIASES.items()})

    display_tz = ZoneInfo(settings.display_timezone)
    target_dt = {datetime.fromisoformat(d).date() for d in target_dates}

    def _map_team(name: Optional[str]) -> Optional[str]:
        return name_to_code.get(_normalize_team_name(name))

    result: List[Dict] = []
    fetched_at = datetime.now(timezone.utc)
    for event in events or []:
        home_name = event.get("home_team")
        away_name = event.get("away_team")
        home_code = _map_team(home_name)
        away_code = _map_team(away_name)
        if not home_code or not away_code:
            logger.warning(
                "[odds_api] 无法映射队名: home=%r away=%r",
                home_name,
                away_name,
            )
            continue

        # 找目标日期内的未完赛比赛
        match = (
            db.query(Match)
            .filter(
                Match.home_team.has(fifa_code=home_code),
                Match.away_team.has(fifa_code=away_code),
                Match.status.in_(["scheduled", "live"]),
            )
            .first()
        )
        if not match or not match.kickoff_at:
            continue
        beijing = match.kickoff_at.replace(tzinfo=timezone.utc).astimezone(display_tz)
        if beijing.date() not in target_dt:
            continue

        # 解析 h2h 市场（多家 bookmaker 取平均）
        h2h_list: List[Dict[str, float]] = []
        over_prices: List[float] = []
        under_prices: List[float] = []
        for bm in event.get("bookmakers", []):
            markets = bm.get("markets") or {}
            if isinstance(markets, list):
                markets = {m.get("key"): m for m in markets}

            h2h = markets.get("h2h")
            if h2h:
                outcomes = {o.get("name"): o.get("price") for o in h2h.get("outcomes", [])}
                home_price = outcomes.get(home_name) or outcomes.get("Home")
                draw_price = outcomes.get("Draw")
                away_price = outcomes.get(away_name) or outcomes.get("Away")
                if home_price and draw_price and away_price:
                    h2h_list.append(
                        {"home_win": float(home_price), "draw": float(draw_price), "away_win": float(away_price)}
                    )

            totals = markets.get("totals")
            if totals:
                for o in totals.get("outcomes", []):
                    price = o.get("price")
                    if price is None:
                        continue
                    name = (o.get("name") or "").lower()
                    if name in ("over", "over 2.5"):
                        over_prices.append(float(price))
                    elif name in ("under", "under 2.5"):
                        under_prices.append(float(price))

        if not h2h_list:
            logger.warning("[odds_api] match_id=%s 无可用 h2h 赔率", match.id)
            continue

        avg = aggregate_multi_bookmaker(h2h_list)
        result.append({
            "match_id": match.id,
            "bookmaker": settings.odds_default_bookmaker,
            "home_win": avg["home_win"],
            "draw": avg["draw"],
            "away_win": avg["away_win"],
            "over_2_5": round(sum(over_prices) / len(over_prices), 2) if over_prices else 1.95,
            "under_2_5": round(sum(under_prices) / len(under_prices), 2) if under_prices else 2.05,
            "source": "the_odds_api",
            "fetched_at": fetched_at,
        })

    logger.info("[odds_api] 解析到 %s 条可用赔率", len(result))
    return result


# === 公共接口 ===
def fetch_upcoming_odds(
    db: Session,
    target_dates: List[str],
    use_cache: bool = True,
) -> List[Dict]:
    """取指定日期列表的未完赛比赛赔率.

    Args:
        db: SQLAlchemy Session
        target_dates: ISO date 列表,如 ["2026-06-11", "2026-06-12"]
        use_cache: 是否使用内存缓存(15min TTL)
    Returns:
        List[Dict]: 见 _fetch_mock 注释
    """
    if not target_dates:
        return []

    cache_key = "odds:" + ",".join(sorted(target_dates))
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    provider = settings.odds_api_provider
    result: List[Dict] = []
    is_mock_provider = provider in ("mock", "seed")

    # 当赔率服务被启用却使用 mock/seed 时给出醒目警告；生产环境（debug=False）直接拒绝，避免误导用户
    if is_mock_provider and settings.odds_api_enabled:
        logger.warning(
            "============================================\n"
            "[odds_api] 当前使用 provider=%s 的模拟赔率，仅供开发/演示！\n"
            "生产环境请务必配置真实赔率 API key（ODDS_API_KEY）与真实 provider。\n"
            "============================================",
            provider,
        )
        if not settings.debug:
            logger.error(
                "[odds_api] 生产环境（debug=False）拒绝使用 mock/seed 赔率，已自动禁用赔率拉取。"
            )
            return []

    if provider == "the_odds_api" and settings.odds_api_enabled:
        result = _fetch_the_odds_api(db, target_dates)
        if not result:
            if not settings.debug and not settings.odds_api_key:
                logger.error(
                    "[odds_api] 生产环境未配置 ODDS_API_KEY，且 provider=the_odds_api 返回空，"
                    "拒绝降级到 mock。"
                )
                return []
            logger.info("[odds_api] The Odds API 返回空,降级 mock")
            result = _fetch_mock(db, target_dates)
    else:
        result = _fetch_mock(db, target_dates)

    if use_cache and result:
        _cache_set(cache_key, result, settings.odds_cache_ttl_seconds)

    return result


def refresh_odds(db: Session, days: Optional[int] = None) -> Dict[str, object]:
    """为 6h 周期调度器拉取未来 N 天赔率并写入 match_odds.

    Args:
        db: SQLAlchemy Session
        days: 拉取未来天数,默认取 settings.odds_fetch_look_ahead_days
    Returns:
        {"fetched": int, "written": int, "dates": ["YYYY-MM-DD", ...], "status": str}
    """
    if not settings.odds_auto_refresh_enabled:
        return {"fetched": 0, "written": 0, "dates": [], "status": "disabled"}

    if days is None:
        days = settings.odds_fetch_look_ahead_days

    display_tz = ZoneInfo(settings.display_timezone)
    now_beijing = datetime.now(display_tz)
    target_dates = [
        (now_beijing + timedelta(days=i)).date().isoformat()
        for i in range(days)
    ]

    fetched = fetch_upcoming_odds(db, target_dates=target_dates, use_cache=True)
    written = upsert_to_match_odds(db, fetched) if fetched else 0
    return {
        "fetched": len(fetched),
        "written": written,
        "dates": target_dates,
        "status": "ok",
    }


def upsert_to_match_odds(db: Session, odds_list: List[Dict]) -> int:
    """把 fetch 返回的赔率字典列表 upsert 到 match_odds 表.

    同 (match_id, bookmaker) 只保留最新一条(覆盖)。
    Returns: 写入条数
    """
    from app.models import MatchOdds

    written = 0
    for o in odds_list:
        if not all(k in o for k in ("match_id", "bookmaker")):
            continue
        existing = (
            db.query(MatchOdds)
            .filter(
                MatchOdds.match_id == o["match_id"],
                MatchOdds.bookmaker == o["bookmaker"],
            )
            .first()
        )
        if existing:
            existing.home_win = o.get("home_win", existing.home_win)
            existing.draw = o.get("draw", existing.draw)
            existing.away_win = o.get("away_win", existing.away_win)
            existing.over_2_5 = o.get("over_2_5", existing.over_2_5)
            existing.under_2_5 = o.get("under_2_5", existing.under_2_5)
            existing.fetched_at = o.get("fetched_at", datetime.now(timezone.utc))
            existing.source = o.get("source", "api")
        else:
            db.add(MatchOdds(
                match_id=o["match_id"],
                bookmaker=o["bookmaker"],
                home_win=o.get("home_win"),
                draw=o.get("draw"),
                away_win=o.get("away_win"),
                over_2_5=o.get("over_2_5"),
                under_2_5=o.get("under_2_5"),
                fetched_at=o.get("fetched_at", datetime.now(timezone.utc)),
                source=o.get("source", "api"),
            ))
        written += 1
    db.commit()
    return written


def service_status() -> Dict:
    """返回赔率服务状态,供 /api/odds/service-status 调用."""
    return {
        "enabled": settings.odds_api_enabled,
        "provider": settings.odds_api_provider,
        "has_api_key": bool(settings.odds_api_key),
        "is_simulated": settings.odds_api_provider in ("mock", "seed"),
        "rate_limit_per_min": settings.odds_api_rate_limit_per_min,
        "cache_ttl_seconds": settings.odds_cache_ttl_seconds,
        "default_bookmaker": settings.odds_default_bookmaker,
        "value_bet_threshold": settings.odds_value_bet_threshold,
    }


# === v0.7.2.3 赔率 vs 模型走势对比 ===
def _decimal_to_vig_free_prob(home: Optional[float], draw: Optional[float], away: Optional[float]) -> Optional[Dict[str, float]]:
    """decimal 赔率 → 去 vig 隐含概率.

    三项均非空才返回,否则 None(单边缺失不能去 vig).
    """
    if not (home and draw and away) or any(o <= 1.0 for o in (home, draw, away)):
        return None
    raw = {
        "home": 1.0 / home,
        "draw": 1.0 / draw,
        "away": 1.0 / away,
    }
    total = sum(raw.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in raw.items()}


def _coerce_utc(value) -> Optional[datetime]:
    """统一 naive/aware datetime 为 UTC,失败返回 None."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_odds_model_history(
    db: Session,
    match_id: int,
    model: str = "blend",
    hours: int = 72,
) -> List[Dict]:
    """对齐 OddsSnapshot + PredictionLog 同一时间窗,返回对比点.

    对齐策略: 对每个 OddsSnapshot 时间点,找 ±5 分钟内最近的 PredictionLog;
    找不到则 model 字段为 None(前端断开线段)。

    Returns:
        List of {ts, market: {home, draw, away}, model: {home, draw, away} | None}
    """
    if hours <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    snapshots = (
        db.query(OddsSnapshot)
        .filter(OddsSnapshot.match_id == match_id)
        .filter(OddsSnapshot.snapshot_at >= cutoff)
        .order_by(OddsSnapshot.snapshot_at.asc())
        .all()
    )

    logs = (
        db.query(PredictionLog)
        .filter(PredictionLog.match_id == match_id)
        .filter(PredictionLog.model_version == model)
        .filter(PredictionLog.predicted_at >= cutoff)
        .order_by(PredictionLog.predicted_at.asc())
        .all()
    )

    points: List[Dict] = []
    for s in snapshots:
        s_ts = _coerce_utc(s.snapshot_at)
        if s_ts is None:
            continue
        market = _decimal_to_vig_free_prob(s.home_win, s.draw, s.away_win)

        # 找 ±5 分钟内最近的 PredictionLog
        nearest_log = None
        nearest_diff = None
        for log in logs:
            log_ts = _coerce_utc(log.predicted_at)
            if log_ts is None:
                continue
            diff = abs((log_ts - s_ts).total_seconds())
            if diff <= 300:  # 5 分钟
                if nearest_diff is None or diff < nearest_diff:
                    nearest_log = log
                    nearest_diff = diff

        model_dict = None
        if nearest_log is not None:
            model_dict = {
                "home": round(nearest_log.pred_home_win, 4),
                "draw": round(nearest_log.pred_draw, 4),
                "away": round(nearest_log.pred_away_win, 4),
            }

        points.append({
            "ts": s_ts.isoformat(),
            "market": (
                {k: round(v, 4) for k, v in market.items()}
                if market else None
            ),
            "model": model_dict,
        })

    return points


def compute_divergence_summary(points: List[Dict]) -> Dict:
    """汇总市场 vs 模型分歧度."""
    if not points:
        return {
            "home_diff_max": 0.0,
            "draw_diff_max": 0.0,
            "away_diff_max": 0.0,
            "market_favored": "home",  # 平局默认
        }

    home_diffs: List[float] = []
    draw_diffs: List[float] = []
    away_diffs: List[float] = []
    home_signed: List[float] = []
    for p in points:
        if p.get("market") is None or p.get("model") is None:
            continue
        home_diffs.append(abs(p["market"]["home"] - p["model"]["home"]))
        draw_diffs.append(abs(p["market"]["draw"] - p["model"]["draw"]))
        away_diffs.append(abs(p["market"]["away"] - p["model"]["away"]))
        home_signed.append(p["market"]["home"] - p["model"]["home"])

    home_diff_max = max(home_diffs) if home_diffs else 0.0
    draw_diff_max = max(draw_diffs) if draw_diffs else 0.0
    away_diff_max = max(away_diffs) if away_diffs else 0.0

    if home_signed:
        avg_signed = sum(home_signed) / len(home_signed)
        if avg_signed > 0.05:
            favored = "home"
        elif avg_signed < -0.05:
            favored = "away"
        else:
            favored = "draw"
    else:
        favored = "home"

    return {
        "home_diff_max": round(home_diff_max, 4),
        "draw_diff_max": round(draw_diff_max, 4),
        "away_diff_max": round(away_diff_max, 4),
        "market_favored": favored,
    }
