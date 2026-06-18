"""从 data/fixtures/matches_raw.json 导入权威开球时间.

背景：worldcup26.ir 的 local_date 字段在 2026 世界杯赛程上与真实 UTC 时间存在偏差，
导致前端显示的北京时间错误。fixtures_raw.json 使用带偏移的 ISO-8601，与官方赛程一致，
因此用它覆盖 matches.kickoff_at，并将 data_source 标记为 fixtures（高优先级），
后续 worldcup26.ir 只刷新比分/状态，不再覆盖开球时间.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main(db_path: str = "data/worldcup2026.db") -> None:
    raw = json.loads(Path("data/fixtures/matches_raw.json").read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    updated = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for m in raw:
        num = m.get("match_number")
        iso = m.get("kickoff_at")
        if not num or not iso:
            continue
        utc_dt = datetime.fromisoformat(iso).astimezone(timezone.utc).replace(tzinfo=None)
        cur.execute(
            "UPDATE matches SET kickoff_at = ?, data_source = ?, last_updated_at = ? WHERE match_number = ?",
            (utc_dt, "fixtures", now, num),
        )
        updated += cur.rowcount
    conn.commit()
    conn.close()
    print(f"✅ 已更新 {updated} 场比赛开球时间为 fixtures 权威时间")


if __name__ == "__main__":
    main()
