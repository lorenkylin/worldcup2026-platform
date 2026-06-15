"""B3: H2H 历史交锋数据回填服务.

把 2018/2022 世界杯种子数据灌入 h2h_historical_matches 表，供 _query_h2h 查询。

策略：idempotent insert — 按 (date, home, away) 唯一键判断是否已存在；
已存在则跳过；不存在则插入。这样可以安全地多次调用。

为什么不直接复用 matches 表：
  - 2018/2022 比赛不是 2026 赛程的一部分，混入会污染赛程 API
  - 2026 已完赛比赛应该优先于历史交锋（更相关）
  - 独立表让种子可独立更新
"""

from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

from data.seed.h2h_seed import H2H_SEED_MATCHES, get_seed_count
from app.models import H2HHistoricalMatch, Team


def _parse_date(s: str) -> datetime:
    """解析 YYYY-MM-DD 格式."""
    return datetime.strptime(s, "%Y-%m-%d")


def backfill_h2h_history(db: Session) -> Dict:
    """从 H2H_SEED_MATCHES 种子数据回填到 h2h_historical_matches.

    Returns:
        {
            "seed_total": int,        # 种子总数
            "inserted": int,          # 本次新增
            "skipped": int,           # 已存在跳过
            "synced_at": iso8601,
        }
    """
    inserted = 0
    skipped = 0

    for item in H2H_SEED_MATCHES:
        match_date = _parse_date(item["date"])

        # 检查是否已存在
        existing = (
            db.query(H2HHistoricalMatch)
            .filter(
                H2HHistoricalMatch.match_date == match_date,
                H2HHistoricalMatch.home_fifa_code == item["home"],
                H2HHistoricalMatch.away_fifa_code == item["away"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        db.add(
            H2HHistoricalMatch(
                home_fifa_code=item["home"],
                away_fifa_code=item["away"],
                home_score=item["hs"],
                away_score=item["as"],
                match_date=match_date,
                competition="FIFA World Cup",
                stage=item.get("stage", ""),
                neutral_venue=item.get("neutral", True),
            )
        )
        inserted += 1

    db.commit()
    return {
        "seed_total": get_seed_count(),
        "inserted": inserted,
        "skipped": skipped,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def query_h2h_history(
    db: Session, code_a: str, code_b: str, lookback: int = 5
) -> List[H2HHistoricalMatch]:
    """查两支队的历史交锋（双向匹配 home/away）.

    返回：按 match_date 倒序的历史交锋记录。
    """
    return (
        db.query(H2HHistoricalMatch)
        .filter(
            (
                (H2HHistoricalMatch.home_fifa_code == code_a)
                & (H2HHistoricalMatch.away_fifa_code == code_b)
            )
            | (
                (H2HHistoricalMatch.home_fifa_code == code_b)
                & (H2HHistoricalMatch.away_fifa_code == code_a)
            )
        )
        .order_by(H2HHistoricalMatch.match_date.desc())
        .limit(lookback)
        .all()
    )
