"""数据库种子脚本.

将 data/fixtures/ 下的原始 JSON 清洗后写入 SQLite。
运行方式：
    python data/seed.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.db import SessionLocal, engine, Base
from app.models import Team, Stadium, Match, Standing
from app.services.prediction import elo_from_fifa_rank


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# 队名兜底修正（英文名 -> 中文名, FIFA 代码, 国旗 emoji）
TEAM_FIXES = {
    "South Korea": ("韩国", "KOR", "🇰🇷"),
    "Bosnia & Herzegovina": ("波黑", "BIH", "🇧🇦"),
    "Haiti": ("海地", "HAI", "🇭🇹"),
    "Curacao": ("库拉索", "CUW", "🇨🇼"),
    "Ivory Coast": ("科特迪瓦", "CIV", "🇨🇮"),
    "Cape Verde": ("佛得角", "CPV", "🇨🇻"),
    "Jordan": ("约旦", "JOR", "🇯🇴"),
    "DR Congo": ("民主刚果", "COD", "🇨🇩"),
}

# 球场所在国判定（基于城市关键词）
MEXICO_CITIES = {"Mexico City", "Guadalajara", "Monterrey"}
CANADA_CITIES = {"Toronto", "Vancouver"}


def _stadium_country(city: str) -> str:
    """根据城市判断国家."""
    if city in MEXICO_CITIES:
        return "Mexico"
    if city in CANADA_CITIES:
        return "Canada"
    return "USA"


def load_json(filename: str) -> list:
    """读取 JSON 文件."""
    path = FIXTURES_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed_teams(db: Session, raw_teams: list[dict]) -> dict[str, int]:
    """写入球队并返回英文名到 ID 的映射."""
    db.query(Team).delete()
    db.commit()

    team_id_map: dict[str, int] = {}
    for t in raw_teams:
        en = t["name_en"]
        name_zh, code, flag = t["name_zh"], t["fifa_code"], t.get("flag_emoji", "")
        if en in TEAM_FIXES:
            name_zh, code, flag = TEAM_FIXES[en]

        # B1: 用 FIFA 排名直接校准 Elo（业内常用对数曲线）
        fifa_rank = t.get("fifa_rank")
        elo = elo_from_fifa_rank(fifa_rank) if fifa_rank else 1500

        team = Team(
            fifa_code=code,
            name_zh=name_zh,
            name_en=en,
            group_name=t.get("group_name", ""),
            flag_emoji=flag,
            fifa_rank=fifa_rank,
            elo_rating=elo,
            recent_form_points=None,  # 后续可从 worldcup26.ir 拉
            recent_goal_diff=None,
        )
        db.add(team)
        db.flush()
        team_id_map[en] = team.id

    db.commit()
    return team_id_map


def seed_stadiums(db: Session, raw_stadiums: list[dict]) -> dict[str, int]:
    """写入球场并返回名称到 ID 的映射."""
    db.query(Stadium).delete()
    db.commit()

    stadium_id_map: dict[str, int] = {}
    for s in raw_stadiums:
        full_name = s["name_en"]
        parts = full_name.rsplit(", ", 1)
        if len(parts) == 2:
            name_en, city = parts
        else:
            name_en, city = full_name, full_name

        stadium = Stadium(
            name_zh=name_en,
            name_en=name_en,
            city=city,
            country=_stadium_country(city),
            timezone=s.get("timezone", "America/New_York"),
        )
        db.add(stadium)
        db.flush()
        stadium_id_map[full_name] = stadium.id

    db.commit()
    return stadium_id_map


def seed_matches(
    db: Session,
    raw_matches: list[dict],
    team_id_map: dict[str, int],
    stadium_id_map: dict[str, int],
) -> None:
    """写入比赛."""
    db.query(Match).delete()
    db.commit()

    for m in raw_matches:
        kickoff = datetime.fromisoformat(m["kickoff_at"]) if m["kickoff_at"] else None
        home_en = m.get("home_team_en")
        away_en = m.get("away_team_en")

        match = Match(
            match_number=m["match_number"],
            stage=m["stage"],
            group_name=m.get("group_name") or None,
            round_number=m.get("round_number", 1),
            kickoff_at=kickoff,
            stadium_id=stadium_id_map.get(m.get("stadium_name")),
            home_team_id=team_id_map.get(home_en) if home_en else None,
            away_team_id=team_id_map.get(away_en) if away_en else None,
            home_team_placeholder=m.get("home_team_placeholder", ""),
            away_team_placeholder=m.get("away_team_placeholder", ""),
            home_score=m.get("home_score"),
            away_score=m.get("away_score"),
            status=m.get("status", "scheduled"),
            time_elapsed=m.get("time_elapsed", ""),
            data_source="worldcupstats.football",
        )
        db.add(match)

    db.commit()


def seed_standings(db: Session, team_id_map: dict[str, int]) -> None:
    """初始化空积分榜."""
    db.query(Standing).delete()
    db.commit()

    teams = db.query(Team).all()
    for team in teams:
        if team.group_name:
            standing = Standing(group_name=team.group_name, team_id=team.id)
            db.add(standing)
    db.commit()


def init_elo_ratings(db: Session) -> None:
    """B1: 兜底用 FIFA 排名 → Elo 对数曲线校准.

    数据已在 seed_teams 中写入 fifa_rank 并直接计算出 elo_rating，
    此处仅作为安全网：当某队 elo_rating 缺失时按排名重新计算。
    """
    for team in db.query(Team).all():
        if not team.elo_rating or team.elo_rating == 1500:
            team.elo_rating = elo_from_fifa_rank(team.fifa_rank)
    db.commit()


def main() -> None:
    """执行种子导入."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        raw_teams = load_json("teams_raw.json")
        raw_stadiums = load_json("stadiums_raw.json")
        raw_matches = load_json("matches_raw.json")

        team_id_map = seed_teams(db, raw_teams)
        stadium_id_map = seed_stadiums(db, raw_stadiums)
        seed_matches(db, raw_matches, team_id_map, stadium_id_map)
        seed_standings(db, team_id_map)
        init_elo_ratings(db)

        print(f"已导入 {len(raw_teams)} 支球队、{len(raw_stadiums)} 座球场、{len(raw_matches)} 场比赛")
    finally:
        db.close()


if __name__ == "__main__":
    main()
