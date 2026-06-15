"""F1 预测结果 LRU 缓存层.

设计目标：
- 预测接口 5 分钟内重复请求 → 直接从 DB 缓存读，跳过全部计算
- 缓存 key = match_id
- 缓存校验 = 两队 fingerprint（recent_form_points + recent_goal_diff），源数据变更自动失效
- TTL = 5 分钟（300 秒）

预期收益：
- 重复请求耗时从 ~80ms 降到 ~5ms（DB 读一条记录）
- 高峰期 100x QPS 压力下，预测服务 CPU 占用降 80%+
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Match, Team, PredictionCache
from app.schemas import PredictionOut


CACHE_TTL_SECONDS = 300  # 5 分钟


def _team_fingerprint(team: Optional[Team]) -> str:
    """计算球队当前状态的指纹，用于缓存命中校验.

    包含字段：
    - elo_rating（B1 已校准）
    - recent_form_points（B2 因子）
    - recent_goal_diff（B2 配套）

    当任一字段变化时，指纹不同 → 缓存失效。
    """
    if team is None:
        return "none"
    payload = f"{team.elo_rating}|{team.recent_form_points}|{team.recent_goal_diff}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


def get_cached_prediction(
    db: Session, match: Match, home: Team, away: Team
) -> Optional[PredictionOut]:
    """尝试从缓存读取预测结果.

    Returns:
        - PredictionOut: 命中且未过期且指纹一致
        - None: 缓存未命中 / 已过期 / 源数据已变更
    """
    cache = (
        db.query(PredictionCache)
        .filter(PredictionCache.match_id == match.id)
        .first()
    )
    if cache is None or not cache.payload_json:
        return None

    # TTL 校验（DB DateTime 为 naive，统一按 UTC 处理）
    generated_at = cache.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - generated_at).total_seconds()
    if age > CACHE_TTL_SECONDS:
        return None

    # 指纹校验：源数据是否已变更
    current_home_fp = _team_fingerprint(home)
    current_away_fp = _team_fingerprint(away)
    if cache.home_team_fingerprint != current_home_fp or cache.away_team_fingerprint != current_away_fp:
        return None

    # 反序列化
    try:
        data = json.loads(cache.payload_json)
        return PredictionOut(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def set_cached_prediction(
    db: Session, match: Match, home: Team, away: Team, prediction: PredictionOut
) -> None:
    """写入预测结果到缓存.

    幂等：同一 match_id 覆盖写入。
    """
    payload_json = prediction.model_dump_json()

    cache = (
        db.query(PredictionCache)
        .filter(PredictionCache.match_id == match.id)
        .first()
    )

    if cache is None:
        cache = PredictionCache(match_id=match.id)
        db.add(cache)

    cache.payload_json = payload_json
    cache.home_team_fingerprint = _team_fingerprint(home)
    cache.away_team_fingerprint = _team_fingerprint(away)
    cache.home_win_prob = prediction.home_win_prob
    cache.draw_prob = prediction.draw_prob
    cache.away_win_prob = prediction.away_win_prob
    cache.expected_home_goals = prediction.expected_home_goals
    cache.expected_away_goals = prediction.expected_away_goals
    cache.recommended_score = prediction.recommended_score
    cache.stars = prediction.stars
    cache.reasons = json.dumps(prediction.reasons, ensure_ascii=False)
    cache.generated_at = datetime.now(timezone.utc)

    db.commit()


def invalidate_cache(db: Session, match_id: int) -> None:
    """手动清除单场比赛缓存（F2 可解释性面板变化时调用）."""
    db.query(PredictionCache).filter(PredictionCache.match_id == match_id).delete()
    db.commit()


def get_cache_stats(db: Session) -> dict:
    """缓存统计信息（调试用）."""
    total = db.query(PredictionCache).count()
    fresh = 0
    stale = 0
    for cache in db.query(PredictionCache).all():
        if cache.generated_at:
            gen = cache.generated_at
            if gen.tzinfo is None:
                gen = gen.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - gen).total_seconds()
            if age <= CACHE_TTL_SECONDS:
                fresh += 1
            else:
                stale += 1
    return {
        "total_cached": total,
        "fresh": fresh,
        "stale": stale,
        "ttl_seconds": CACHE_TTL_SECONDS,
    }
