"""数据质量校验工具（v0.14.1）.

对外部数据源返回的原始数据做“使用前分析”：去重、时效校验、状态机保护，
确保写入 DB 的是最新、无重复、时间合理的记录。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 状态推进顺序（数字越大越“晚”）
STATUS_ORDER = {"scheduled": 0, "live": 1, "finished": 2}

# 2026 世界杯合理时间窗：揭幕战前 30 天 ~ 决赛后 7 天
SEASON_WINDOW_START = datetime(2026, 5, 12, tzinfo=timezone.utc)
SEASON_WINDOW_END = datetime(2026, 7, 26, tzinfo=timezone.utc)


class DataQualityError(Exception):
    """数据质量不满足要求时抛出，供上层回退或记录."""


# 数据源优先级：数字越大越权威，低优先级源不应覆盖高优先级源
SOURCE_PRIORITY = {
    "manual": 3,
    "api-football": 2,
    "worldcup26.ir": 1,
}


def can_overwrite(
    existing_source: Optional[str],
    candidate_source: str,
    existing_updated_at: Optional[datetime] = None,
    stale_threshold_seconds: float = 6 * 3600,
    now: Optional[datetime] = None,
) -> bool:
    """判断 candidate_source 是否可以覆盖 existing_source 的数据.

    规则：
    1. 同优先级允许覆盖（取最新）。
    2. 手动录入（manual）永远不被自动源覆盖。
    3. 其他高优先级数据默认 6h 内不被低优先级覆盖；超过 6h 视为过期，允许兜底源刷新。
    4. 无数据源记录视为可覆盖。
    """
    if existing_source == "manual":
        return False
    existing_rank = SOURCE_PRIORITY.get(existing_source, 0)
    candidate_rank = SOURCE_PRIORITY.get(candidate_source, 0)
    if candidate_rank >= existing_rank:
        return True
    if existing_updated_at is None:
        return True
    now = now or now_utc()
    age = (now - as_utc(existing_updated_at)).total_seconds()
    return age > stale_threshold_seconds


def parse_iso_timestamp(value: object) -> Optional[datetime]:
    """安全解析 ISO 时间字符串，返回 UTC aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def now_utc() -> datetime:
    """当前 UTC 时间."""
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """转为 UTC aware datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_fresh(
    recorded_at: Optional[datetime],
    max_age_seconds: Optional[float] = None,
    now: Optional[datetime] = None,
) -> bool:
    """判断记录时间是否新鲜.

    Args:
        recorded_at: 记录产生时间。
        max_age_seconds: 允许的最大年龄（秒）。None 表示不检查。
        now: 用于比对的当前时间，默认 now_utc()。

    Returns:
        True 当且仅当时间戳合理且未过期；时间戳缺失时视为无法判断，返回 True。
    """
    if recorded_at is None or max_age_seconds is None:
        return True
    rec = as_utc(recorded_at)
    if rec is None:
        return True
    now = now or now_utc()
    age = (now - rec).total_seconds()
    # 允许 60 秒时钟偏移，拒绝“未来”超过 60 秒的数据
    return -60.0 <= age <= max_age_seconds


def filter_fresh(
    items: Iterable[T],
    timestamp_func: Callable[[T], object],
    max_age_seconds: float,
    now: Optional[datetime] = None,
) -> List[T]:
    """过滤出过期的记录并记录日志."""
    now = now or now_utc()
    fresh: List[T] = []
    stale = 0
    for item in items:
        ts = parse_iso_timestamp(timestamp_func(item))
        if ts is None or is_fresh(ts, max_age_seconds, now):
            fresh.append(item)
        else:
            stale += 1
    if stale:
        logger.warning("数据质量：过滤掉 %d 条过期记录（max_age=%ss）", stale, max_age_seconds)
    return fresh


def deduplicate(
    items: Iterable[T],
    key_func: Callable[[T], Optional[str]],
    keep: str = "last",
) -> List[T]:
    """按 key 去重，保留 first 或 last.

    返回顺序与首次/末次出现一致（keep=last 时按最后出现顺序）。
    """
    if keep not in ("first", "last"):
        raise ValueError("keep 必须是 'first' 或 'last'")

    seen: dict[str, T] = {}
    order: List[str] = []
    for item in items:
        key = key_func(item)
        if key is None:
            continue
        if key not in seen:
            order.append(key)
        if keep == "last":
            seen[key] = item
        else:
            seen.setdefault(key, item)
    return [seen[k] for k in order]


def find_duplicates(
    items: Iterable[T],
    key_func: Callable[[T], Optional[str]],
) -> List[str]:
    """返回重复 key 列表."""
    seen: set[str] = set()
    dups: set[str] = set()
    for item in items:
        key = key_func(item)
        if key is None:
            continue
        if key in seen:
            dups.add(key)
        seen.add(key)
    return sorted(dups)


def assert_unique(
    items: Iterable[T],
    key_func: Callable[[T], Optional[str]],
    label: str = "items",
    raise_on_dup: bool = False,
) -> List[str]:
    """检查唯一性.

    Args:
        raise_on_dup: True 则发现重复时抛出 DataQualityError；False 仅记录 warning。

    Returns:
        重复 key 列表（供调用方决策）。
    """
    dups = find_duplicates(items, key_func)
    if dups:
        msg = f"{label} 发现重复 key: {dups[:10]}"
        if raise_on_dup:
            raise DataQualityError(msg)
        logger.warning("数据质量：%s", msg)
    return dups


def is_within_season_window(dt: Optional[datetime]) -> bool:
    """判断比赛时间是否在 2026 世界杯合理窗口内."""
    if dt is None:
        return False
    utc_dt = as_utc(dt)
    if utc_dt is None:
        return False
    return SEASON_WINDOW_START <= utc_dt <= SEASON_WINDOW_END


def validate_kickoff_window(
    dt: Optional[datetime],
    context: str = "kickoff",
) -> bool:
    """校验开球/事件时间合理性，太远过去或未来则记录警告并返回 False."""
    if dt is None:
        logger.warning("数据质量：%s 时间缺失", context)
        return False
    utc_dt = as_utc(dt)
    if utc_dt is None:
        return False
    if not is_within_season_window(utc_dt):
        logger.warning(
            "数据质量：%s 时间 %s 不在 2026 世界杯窗口 %s ~ %s 内",
            context,
            utc_dt.isoformat(),
            SEASON_WINDOW_START.date().isoformat(),
            SEASON_WINDOW_END.date().isoformat(),
        )
        return False
    return True


def is_status_transition_allowed(current: Optional[str], new: str) -> bool:
    """状态是否只允许向前推进（scheduled -> live -> finished）.

    未知状态放行，由调用方自行判断。
    """
    cur_rank = STATUS_ORDER.get(current, -1)
    new_rank = STATUS_ORDER.get(new, -1)
    if cur_rank == -1 or new_rank == -1:
        return True
    return new_rank >= cur_rank


def should_update_field(
    existing_value: object,
    candidate_value: object,
    existing_updated_at: Optional[datetime],
    candidate_updated_at: Optional[datetime],
    allow_overwrite_none: bool = True,
) -> bool:
    """综合判断是否应该用候选值覆盖现有值.

    规则：
    1. 候选值为 None 时不覆盖（除非 allow_overwrite_none=True 且现有值也是 None，但无意义）。
    2. 候选值与现有值相同不覆盖。
    3. 若候选时间戳更新，允许覆盖；若更旧，拒绝覆盖。
    4. 没有时间戳时，默认允许覆盖（外部已决定使用新数据）。
    """
    if candidate_value is None:
        return False
    if existing_value == candidate_value:
        return False
    if not allow_overwrite_none and existing_value is not None:
        # 已有值且不允许用非 None 覆盖？实际语义是：若允许覆盖 None，则 existing=None 时可写
        pass
    existing_dt = as_utc(existing_updated_at)
    candidate_dt = as_utc(candidate_updated_at)
    if existing_dt and candidate_dt:
        # 候选数据比现有数据旧，不覆盖
        if candidate_dt <= existing_dt:
            return False
    return True


def source_quality_summary(
    items: Iterable[T],
    key_func: Callable[[T], Optional[str]],
    timestamp_func: Optional[Callable[[T], object]] = None,
    max_age_seconds: Optional[float] = None,
) -> dict:
    """对一批原始数据做质量摘要，用于多源编排决策."""
    item_list = list(items)
    total = len(item_list)
    dups = find_duplicates(item_list, key_func)
    fresh_count = total
    if timestamp_func and max_age_seconds:
        now = now_utc()
        fresh_count = sum(
            1
            for it in item_list
            if is_fresh(parse_iso_timestamp(timestamp_func(it)), max_age_seconds, now)
        )
    return {
        "total": total,
        "duplicates": len(dups),
        "duplicate_keys": dups[:10],
        "fresh": fresh_count,
        "stale": total - fresh_count,
        "quality_ok": len(dups) == 0 and (fresh_count == total or max_age_seconds is None),
    }
