"""B 组：数据完整性回归测试.

确保 seed + 同步后 DB 始终符合 FIFA 2026 真实赛制：
- 48 支真实球队，无 placeholder
- 48 条积分榜记录
- 104 场比赛：72 场小组赛 + 32 场淘汰赛
"""
import importlib.util
import json
from pathlib import Path

import pytest

from app.models import Team, Match, Standing


def _load_seed_module():
    """data/seed.py 与 data/seed/ 子包同名，直接用 importlib 加载模块文件."""
    seed_path = Path(__file__).resolve().parent.parent / "data" / "seed.py"
    spec = importlib.util.spec_from_file_location("_seed_data_module", str(seed_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fully_seeded_db(db_session):
    """用 data/seed.py 的函数把临时 DB 灌满真实 fixture 数据."""
    seed = _load_seed_module()

    fixtures_dir = Path(__file__).resolve().parent.parent / "data" / "fixtures"
    raw_teams = json.loads((fixtures_dir / "teams_raw.json").read_text(encoding="utf-8"))
    raw_stadiums = json.loads((fixtures_dir / "stadiums_raw.json").read_text(encoding="utf-8"))
    raw_matches = json.loads((fixtures_dir / "matches_raw.json").read_text(encoding="utf-8"))

    team_id_map = seed.seed_teams(db_session, raw_teams)
    stadium_id_map, stadium_tz_map = seed.seed_stadiums(db_session, raw_stadiums)
    seed.seed_matches(db_session, raw_matches, team_id_map, stadium_id_map, stadium_tz_map)
    seed.seed_standings(db_session, team_id_map)
    seed.init_elo_ratings(db_session)
    return db_session


def test_team_count_and_no_placeholders(fully_seeded_db):
    db = fully_seeded_db
    teams = db.query(Team).all()
    assert len(teams) == 48, f"球队数应为 48,实际 {len(teams)}"

    groups = {t.group_name for t in teams}
    assert groups == set("ABCDEFGHIJKL"), f"球队分组异常: {groups}"

    for t in teams:
        assert t.fifa_code, f"球队 {t.name_en} 缺 fifa_code"
        assert not t.name_en.startswith("Team "), f"发现 placeholder 球队: {t.name_en}"
        # 早期 seed 曾用 A1-A8/B1-B8 等占位 code
        assert not (len(t.fifa_code) == 2 and t.fifa_code[0] in "ABCDEFGHIJKL" and t.fifa_code[1].isdigit()), \
            f"发现占位 fifa_code: {t.fifa_code} ({t.name_en})"


def test_standing_count_matches_real_teams(fully_seeded_db):
    db = fully_seeded_db
    standings = db.query(Standing).all()
    assert len(standings) == 48, f"积分榜应为 48 条,实际 {len(standings)}"
    groups = {s.group_name for s in standings}
    assert groups == set("ABCDEFGHIJKL"), f"积分榜分组异常: {groups}"


def test_match_count_and_structure(fully_seeded_db):
    db = fully_seeded_db
    matches = db.query(Match).all()
    assert len(matches) == 104, f"比赛数应为 104,实际 {len(matches)}"

    # seed fixture 中所有比赛的 stage 都是 "小组赛",用 group_name 区分轮次
    group_set = set("ABCDEFGHIJKL")
    group_matches = [m for m in matches if (m.group_name or "") in group_set]
    knockout_matches = [m for m in matches if (m.group_name or "") == ""]

    assert len(group_matches) == 72, f"小组赛应为 72 场,实际 {len(group_matches)}"
    assert len(knockout_matches) == 32, f"淘汰赛应为 32 场,实际 {len(knockout_matches)}"

    # 小组赛必须有 A-L 分组,且每组 6 场
    group_counts = {}
    for m in group_matches:
        group_counts[m.group_name] = group_counts.get(m.group_name, 0) + 1
    for g in "ABCDEFGHIJKL":
        assert group_counts.get(g) == 6, f"{g} 组应为 6 场,实际 {group_counts.get(g)}"

    # 所有比赛都有开球时间
    for m in matches:
        assert m.kickoff_at is not None, f"match_id={m.id} 缺少 kickoff_at"


def test_no_group_z_anomaly(fully_seeded_db):
    db = fully_seeded_db
    anomaly = db.query(Match).filter(Match.group_name == "Z").all()
    assert len(anomaly) == 0, f"发现 group_name='Z' 异常比赛: {len(anomaly)} 场"
