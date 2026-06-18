"""v0.13.0 一次性数据清理脚本.

清理本地/生产 SQLite 中因 seed + worldcup26.ir 同步产生的重复/过时数据：
- 删除占位球队（Team A1 / fifa_code=A1 等）
- 合并重复球场（同名变体）
- 删除 match_number 不在 1-104 范围内的非手动孤儿比赛
- 重建 standings，只保留真实 48 队

用法:
    python scripts/cleanup_v013_data.py --dry-run   # 默认，只打印
    python scripts/cleanup_v013_data.py --apply     # 真正执行
"""

import argparse
import re
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.db import SessionLocal
from app.models import Match, Standing, Team


def _normalize_stadium_name(name: str) -> str:
    """球场名规范化：去空格、去尾部的 Stadium，用于聚类重复.

    保留 Field，避免 "GEHA Field at Arrowhead Stadium" 与
    "GEHA Field at Arrowhead" 被分到不同组。
    """
    s = name.strip().lower()
    s = re.sub(r"\s+stadium\s*$", "", s)
    return s


def _normalize_country(country: str) -> str:
    """国家名规范化，处理 USA/United States 等变体."""
    s = (country or "").strip().lower()
    if s in ("usa", "us", "united states of america"):
        return "united states"
    return s


def _get_counts(db) -> dict:
    return {
        "teams": db.execute(text("SELECT COUNT(*) FROM teams")).scalar(),
        "stadiums": db.execute(text("SELECT COUNT(*) FROM stadiums")).scalar(),
        "matches": db.execute(text("SELECT COUNT(*) FROM matches")).scalar(),
        "standings": db.execute(text("SELECT COUNT(*) FROM standings")).scalar(),
    }


def _find_placeholder_team_ids(db) -> list[int]:
    """查找占位球队 ID."""
    rows = db.execute(
        text(
            """
            SELECT id FROM teams
            WHERE name_en LIKE 'Team %'
               OR fifa_code GLOB '[A-L][1-8]'
            ORDER BY id
            """
        )
    ).fetchall()
    return [r[0] for r in rows]


def _find_duplicate_stadium_groups(db) -> list[list[tuple[int, str]]]:
    """按规范化名称 + 城市 + 国家分组，返回有重复的组."""
    rows = db.execute(
        text("SELECT id, name_en, city, country FROM stadiums ORDER BY id")
    ).fetchall()
    groups: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for rid, name, city, country in rows:
        key = (
            _normalize_stadium_name(name),
            (city or "").strip().lower(),
            _normalize_country(country),
        )
        groups.setdefault(key, []).append((rid, name))
    return [g for g in groups.values() if len(g) > 1]


def _find_orphan_match_ids(db) -> list[tuple[int, int, str]]:
    """查找 match_number 不在 1-104 的孤儿比赛，返回 (id, match_number, data_source)."""
    rows = db.execute(
        text(
            """
            SELECT id, match_number, data_source FROM matches
            WHERE match_number < 1 OR match_number > 104
            ORDER BY id
            """
        )
    ).fetchall()
    return [(r[0], r[1], r[2] or "") for r in rows]


def _rebuild_standings(db) -> int:
    """删除旧 standings，为真实 48 队重建空积分记录."""
    db.execute(text("DELETE FROM standings"))
    db.execute(
        text(
            """
            INSERT INTO standings (group_name, team_id, played, won, drawn, lost, goals_for, goals_against, points)
            SELECT group_name, id, 0, 0, 0, 0, 0, 0, 0
            FROM teams
            WHERE group_name IS NOT NULL AND group_name != ''
            """
        )
    )
    return db.execute(text("SELECT COUNT(*) FROM standings")).scalar()


def cleanup(db, apply: bool) -> dict:
    """执行清理逻辑，返回变更摘要."""
    before = _get_counts(db)
    changes = {
        "placeholder_teams_deleted": 0,
        "duplicate_stadiums_merged": 0,
        "orphan_matches_deleted": 0,
        "standings_rebuilt": 0,
    }

    # 1) 合并重复球场（先处理，因为后面删除球队/比赛不涉及球场，但比赛会引用球场）
    dup_groups = _find_duplicate_stadium_groups(db)
    for group in dup_groups:
        group.sort(key=lambda x: x[0])  # 按 id 升序，保留最小 id
        keep_id, keep_name = group[0]
        for dup_id, dup_name in group[1:]:
            print(f"[stadium] 合并重复球场: #{dup_id} '{dup_name}' -> #{keep_id} '{keep_name}'")
            if apply:
                db.execute(
                    text("UPDATE matches SET stadium_id = :keep_id WHERE stadium_id = :dup_id"),
                    {"keep_id": keep_id, "dup_id": dup_id},
                )
                db.execute(text("DELETE FROM stadiums WHERE id = :dup_id"), {"dup_id": dup_id})
            changes["duplicate_stadiums_merged"] += 1

    # 2) 删除占位球队前，先把引用它们的比赛 team_id 置空（避免 FK 冲突）
    placeholder_ids = _find_placeholder_team_ids(db)
    if placeholder_ids:
        print(f"[teams] 发现占位球队 {len(placeholder_ids)} 个: {placeholder_ids[:10]}{'...' if len(placeholder_ids) > 10 else ''}")
        if apply:
            db.query(Match).filter(Match.home_team_id.in_(placeholder_ids)).update(
                {"home_team_id": None}, synchronize_session=False
            )
            db.query(Match).filter(Match.away_team_id.in_(placeholder_ids)).update(
                {"away_team_id": None}, synchronize_session=False
            )
            db.query(Team).filter(Team.id.in_(placeholder_ids)).delete(
                synchronize_session=False
            )
        changes["placeholder_teams_deleted"] = len(placeholder_ids)

    # 3) 删除孤儿比赛
    orphan_rows = _find_orphan_match_ids(db)
    if orphan_rows:
        print(f"[matches] 发现孤儿比赛 {len(orphan_rows)} 个:")
        for oid, onum, src in orphan_rows:
            print(f"  - id={oid} match_number={onum} data_source={src!r}")
        if apply:
            orphan_ids = [oid for oid, _, _ in orphan_rows]
            db.query(Match).filter(Match.id.in_(orphan_ids)).delete(
                synchronize_session=False
            )
        changes["orphan_matches_deleted"] = len(orphan_rows)

    # 4) 重建 standings
    print("[standings] 重建积分榜...")
    if apply:
        count = _rebuild_standings(db)
        changes["standings_rebuilt"] = count
        db.commit()
    else:
        # dry-run 时只估算（排除占位球队）
        count = db.execute(
            text(
                """
                SELECT COUNT(*) FROM teams
                WHERE group_name IS NOT NULL AND group_name != ''
                  AND name_en NOT LIKE 'Team %'
                  AND fifa_code NOT GLOB '[A-L][1-8]'
                """
            )
        ).scalar()
        changes["standings_rebuilt"] = count

    after = _get_counts(db) if apply else before  # dry-run 不提交，计数不变
    return {
        "before": before,
        "after": after,
        "changes": changes,
    }


def main() -> int:
    # Windows 控制台默认 gbk，强制 utf-8 避免中文输出乱码
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="v0.13.0 数据清理")
    parser.add_argument("--apply", action="store_true", help="真正执行清理（默认 --dry-run）")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = cleanup(db, apply=args.apply)
        print("\n清理摘要:")
        print(f"  模式: {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"  teams:    {result['before']['teams']} -> {result['after']['teams']}")
        print(f"  stadiums: {result['before']['stadiums']} -> {result['after']['stadiums']}")
        print(f"  matches:  {result['before']['matches']} -> {result['after']['matches']}")
        print(f"  standings:{result['before']['standings']} -> {result['after']['standings']}")
        print(f"  变更: {result['changes']}")

        if not args.apply:
            print("\n这是干跑。如确认无误，请加 --apply 执行。")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
