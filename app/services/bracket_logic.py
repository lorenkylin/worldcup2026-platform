"""2026 世界杯淘汰赛对阵生成逻辑.

2026 扩军后规则：
- 48 队分 12 组（A-L），每组前 2 名 + 8 个成绩最好的第 3 名进入 32 强。
- R32 共 16 场（Match 73-88），按 FIFA Annex C 对阵表配对。
- R16/QF/SF/Final 由 R32 胜者推进（Match 89-104）。

本模块所有逻辑只依赖现有 DB（teams + standings + matches），零外部 API。
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Match, Standing, Team
from app.services.elo import match_prob


# === 2026 R32 对阵表（FIFA Annex C） ===
# 占位符格式：
#   "1A"  -> A 组第 1 名
#   "2A"  -> A 组第 2 名
#   "3ABDF" -> 候选小组 A/B/D/F 中成绩最好的第 3 名（每个槽位候选集合不同）
R32_MATCHUPS: List[Dict[str, str]] = [
    {"match_number": "73", "home": "2A", "away": "2B"},
    {"match_number": "74", "home": "1E", "away": "3ABCDF"},  # A/B/C/D/F
    {"match_number": "75", "home": "1F", "away": "2C"},
    {"match_number": "76", "home": "1C", "away": "2F"},
    {"match_number": "77", "home": "1I", "away": "3CDFGH"},  # C/D/F/G/H
    {"match_number": "78", "home": "2E", "away": "2I"},
    {"match_number": "79", "home": "1A", "away": "3CEFHI"},  # C/E/F/H/I
    {"match_number": "80", "home": "1L", "away": "3EHIJK"},  # E/H/I/J/K
    {"match_number": "81", "home": "1D", "away": "3BEFIJ"},  # B/E/F/I/J
    {"match_number": "82", "home": "1G", "away": "3AEHIJ"},  # A/E/H/I/J
    {"match_number": "83", "home": "2K", "away": "2L"},
    {"match_number": "84", "home": "1H", "away": "2J"},
    {"match_number": "85", "home": "1B", "away": "3EFGIJ"},  # E/F/G/I/J
    {"match_number": "86", "home": "1J", "away": "2H"},
    {"match_number": "87", "home": "1K", "away": "3DEIJL"},  # D/E/I/J/L
    {"match_number": "88", "home": "2D", "away": "2G"},
]


@dataclass
class StandingRow:
    """小组排名行（与 DB Standing + Team 组合）."""

    team: Team
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against

    def to_dict(self) -> Dict:
        return {
            "team_id": self.team.id,
            "fifa_code": self.team.fifa_code,
            "name_zh": self.team.name_zh,
            "name_en": self.team.name_en,
            "flag_emoji": self.team.flag_emoji,
            "group_name": self.team.group_name,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "goal_diff": self.goal_diff,
            "points": self.points,
        }


@dataclass
class BracketSlot:
    """一个对阵槽位（R32 的一场）."""

    match_number: int
    stage: str
    home_source: str
    away_source: str
    home_team: Optional[Team] = None
    away_team: Optional[Team] = None
    home_placeholder: str = ""
    away_placeholder: str = ""

    def to_dict(self) -> Dict:
        return {
            "match_number": self.match_number,
            "stage": self.stage,
            "home": {
                "source": self.home_source,
                "team": self._team_dict(self.home_team),
                "placeholder": self.home_placeholder,
            },
            "away": {
                "source": self.away_source,
                "team": self._team_dict(self.away_team),
                "placeholder": self.away_placeholder,
            },
        }

    @staticmethod
    def _team_dict(team: Optional[Team]) -> Optional[Dict]:
        if team is None:
            return None
        return {
            "id": team.id,
            "fifa_code": team.fifa_code,
            "name_zh": team.name_zh,
            "name_en": team.name_en,
            "flag_emoji": team.flag_emoji,
            "elo_rating": team.elo_rating,
        }


def _sort_standing_rows(rows: List[StandingRow]) -> List[StandingRow]:
    """按积分 > 净胜球 > 进球 降序排列.

    v0.3.0 实现前 3 项 tie-breaker。更复杂的直接交锋/公平竞赛/抽签留到后续。
    """
    return sorted(
        rows,
        key=lambda r: (r.points, r.goal_diff, r.goals_for),
        reverse=True,
    )


def compute_group_standings(db: Session) -> Dict[str, List[StandingRow]]:
    """计算 12 个小组的完整排名.

    Returns:
        {group_name: [StandingRow(第1名), StandingRow(第2名), ...]}
    """
    teams: List[Team] = db.query(Team).all()
    standings: List[Standing] = db.query(Standing).all()
    standing_map: Dict[int, Standing] = {s.team_id: s for s in standings}

    grouped: Dict[str, List[StandingRow]] = {}
    for team in teams:
        s = standing_map.get(team.id)
        row = StandingRow(
            team=team,
            played=s.played if s else 0,
            won=s.won if s else 0,
            drawn=s.drawn if s else 0,
            lost=s.lost if s else 0,
            goals_for=s.goals_for if s else 0,
            goals_against=s.goals_against if s else 0,
            points=s.points if s else 0,
        )
        grouped.setdefault(team.group_name, []).append(row)

    for group_name in grouped:
        grouped[group_name] = _sort_standing_rows(grouped[group_name])

    return grouped


def rank_third_place_teams(
    standings: Dict[str, List[StandingRow]],
) -> List[StandingRow]:
    """对 12 个小组第 3 名统一排名，取前 8 晋级.

    排名规则与小组赛相同：积分 > 净胜球 > 进球。
    """
    thirds = []
    for group_name in sorted(standings.keys()):
        rows = standings[group_name]
        if len(rows) >= 3:
            thirds.append(rows[2])
    return _sort_standing_rows(thirds)[:8]


def _parse_source(source: str) -> Tuple[str, Optional[List[str]]]:
    """解析占位符.

    Returns:
        (kind, candidates) 其中 kind 为 "1"/"2"/"3"，candidates 是候选小组列表（仅 kind==3）。
    """
    if source.startswith("3"):
        # e.g. "3ABCDF" -> kind="3", candidates=["A","B","C","D","F"]
        candidates = list(source[1:])
        return "3", candidates
    return source[0], None


def _resolve_team(
    source: str,
    standings: Dict[str, List[StandingRow]],
    third_places: List[StandingRow],
    assigned_thirds: Dict[str, str],
) -> Tuple[Optional[Team], str]:
    """把占位符解析为具体球队.

    Returns:
        (team, placeholder_text)
    """
    kind, candidates = _parse_source(source)

    if kind in ("1", "2"):
        group_name = source[1:]
        rank = int(kind) - 1  # 0-based index
        rows = standings.get(group_name, [])
        if len(rows) > rank:
            row = rows[rank]
            return row.team, source
        return None, source

    # kind == "3": 最佳第三，需要从 assigned_thirds 中查找分配结果
    # 找到当前槽位被分配了哪个小组的第三
    for slot_source, group_name in assigned_thirds.items():
        if slot_source == source:
            rows = standings.get(group_name, [])
            if len(rows) >= 3:
                return rows[2].team, f"最佳第三（{''.join(candidates)}）"
            return None, f"最佳第三（{''.join(candidates)}）"

    # 尚未分配（小组赛未结束或该小组第三未晋级）
    return None, f"最佳第三（{''.join(candidates)}）"


def _assign_third_place_slots(
    third_places: List[StandingRow],
) -> Dict[str, str]:
    """把 8 个晋级的小组第三分配到 8 个 R32 槽位.

    策略（v0.3.0 简化版）：
    1. 按第三名的综合成绩排名从高到低处理。
    2. 对每个第三，找到所有候选集合包含其所在小组的槽位。
    3. 选择 match_number 最小编号的可用槽位。

    注意：这不是 FIFA Annex C 的完整官方规则，而是工程上的贪心近似；
    后续可引入官方优先级表做精确映射。
    """
    # 槽位 -> 候选小组集合
    slot_candidates: Dict[str, List[str]] = {}
    for m in R32_MATCHUPS:
        away = m["away"]
        if away.startswith("3"):
            slot_candidates[away] = list(away[1:])

    assigned: Dict[str, str] = {}  # slot_source -> group_name
    used_slots: set = set()

    for third in third_places:
        group_name = third.team.group_name
        # 可放入的槽位（候选集合包含本小组，且尚未被占用）
        eligible = [
            slot
            for slot, candidates in slot_candidates.items()
            if group_name in candidates and slot not in used_slots
        ]
        if eligible:
            # 选择 match_number 最小的槽位
            eligible.sort(key=lambda s: int(next(m["match_number"] for m in R32_MATCHUPS if m["away"] == s)))
            chosen = eligible[0]
            assigned[chosen] = group_name
            used_slots.add(chosen)

    return assigned


def resolve_r32_matchups(
    standings: Dict[str, List[StandingRow]],
    third_places: List[StandingRow],
) -> List[BracketSlot]:
    """生成 R32（Match 73-88）的真实对阵."""
    assigned_thirds = _assign_third_place_slots(third_places)
    slots: List[BracketSlot] = []

    for m in R32_MATCHUPS:
        home_source = m["home"]
        away_source = m["away"]
        home_team, home_placeholder = _resolve_team(
            home_source, standings, third_places, assigned_thirds
        )
        away_team, away_placeholder = _resolve_team(
            away_source, standings, third_places, assigned_thirds
        )
        slots.append(
            BracketSlot(
                match_number=int(m["match_number"]),
                stage="R32",
                home_source=home_source,
                away_source=away_source,
                home_team=home_team,
                away_team=away_team,
                home_placeholder=home_placeholder,
                away_placeholder=away_placeholder,
            )
        )

    return slots


def _prediction_for_match(
    home_team: Optional[Team], away_team: Optional[Team]
) -> Optional[Dict]:
    """用 Elo 模型计算两队 1X2 概率.

    淘汰赛有加时/点球，但 v0.3.0 先按 90 分钟概率展示。
    """
    if home_team is None or away_team is None:
        return None
    if home_team.elo_rating is None or away_team.elo_rating is None:
        return None

    probs = match_prob(home_team.elo_rating, away_team.elo_rating)
    return {
        "home_win": round(probs["winA"], 4),
        "draw": round(probs["draw"], 4),
        "away_win": round(probs["winB"], 4),
        "expected_home_goals": round(probs["expectedGoalsA"], 2),
        "expected_away_goals": round(probs["expectedGoalsB"], 2),
    }


def _group_stage_finished(db: Session) -> bool:
    """判断小组赛是否全部结束（match_number 1-72 全部 finished）."""
    group_matches = db.query(Match).filter(Match.match_number <= 72).all()
    if not group_matches:
        return False
    return all(m.status == "finished" for m in group_matches)


def build_bracket(db: Session) -> Dict:
    """构建完整淘汰赛对阵树（核心 API 用）.

    Returns:
        {
            "generated_at": "...",
            "group_stage_finished": bool,
            "rounds": {
                "r32": [...],
                "r16": [...],
                "qf": [...],
                "sf": [...],
                "third_place": {...},
                "final": {...},
            }
        }
    """
    standings = compute_group_standings(db)
    third_places = rank_third_place_teams(standings)
    r32_slots = resolve_r32_matchups(standings, third_places)

    # 读取 DB 中已有的淘汰赛占位记录（match_number 73-104）
    knockout_matches: Dict[int, Match] = {
        m.match_number: m
        for m in db.query(Match).filter(Match.match_number >= 73).all()
    }

    rounds: Dict[str, List[Dict]] = {
        "r32": [],
        "r16": [],
        "qf": [],
        "sf": [],
        "third_place": None,
        "final": None,
    }

    for slot in r32_slots:
        match = knockout_matches.get(slot.match_number)
        node = slot.to_dict()
        node["kickoff_at"] = match.kickoff_at.isoformat() if match else None
        node["prediction"] = _prediction_for_match(slot.home_team, slot.away_team)
        rounds["r32"].append(node)

    # R16/SF/Final 当前仍用 DB 中的占位（需等 R32 结果）
    # 但 API 仍返回这些比赛的基本信息 + 占位文本
    for m in db.query(Match).filter(Match.match_number >= 89).order_by(Match.match_number).all():
        node = {
            "match_number": m.match_number,
            "stage": m.stage,
            "home": {
                "source": m.home_team_placeholder or "TBD",
                "team": BracketSlot._team_dict(m.home_team),
                "placeholder": m.home_team_placeholder or "待定",
            },
            "away": {
                "source": m.away_team_placeholder or "TBD",
                "team": BracketSlot._team_dict(m.away_team),
                "placeholder": m.away_team_placeholder or "待定",
            },
            "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
            "prediction": _prediction_for_match(m.home_team, m.away_team),
        }
        if m.match_number in (101, 102):
            rounds["sf"].append(node)
        elif m.match_number in (97, 98, 99, 100):
            rounds["qf"].append(node)
        elif m.match_number in range(89, 97):
            rounds["r16"].append(node)
        elif m.match_number == 103:
            rounds["third_place"] = node
        elif m.match_number == 104:
            rounds["final"] = node

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "group_stage_finished": _group_stage_finished(db),
        "rounds": rounds,
    }


def update_knockout_matches(db: Session, slots: List[BracketSlot]) -> Dict:
    """把 R32 对阵计算结果写回 matches 表.

    只更新 match_number 73-88 的 home_team_id / away_team_id / placeholder 字段。
    后续轮次（89-104）由比赛结果驱动，不在此处更新。
    """
    match_map: Dict[int, Match] = {
        m.match_number: m
        for m in db.query(Match).filter(Match.match_number >= 73, Match.match_number <= 88).all()
    }

    updated = 0
    for slot in slots:
        match = match_map.get(slot.match_number)
        if not match:
            continue
        match.home_team_id = slot.home_team.id if slot.home_team else None
        match.away_team_id = slot.away_team.id if slot.away_team else None
        match.home_team_placeholder = slot.home_placeholder or slot.home_source
        match.away_team_placeholder = slot.away_placeholder or slot.away_source
        match.last_updated_at = datetime.now(timezone.utc)
        updated += 1

    db.commit()
    return {"updated": updated}


def rebuild_bracket(db: Session) -> Dict:
    """重新计算并持久化淘汰赛对阵.

    供 admin rebuild endpoint 调用。
    """
    standings = compute_group_standings(db)
    third_places = rank_third_place_teams(standings)
    r32_slots = resolve_r32_matchups(standings, third_places)
    update_result = update_knockout_matches(db, r32_slots)
    bracket = build_bracket(db)
    return {
        "ok": True,
        "updated_matches": update_result["updated"],
        "group_stage_finished": bracket["group_stage_finished"],
        "generated_at": bracket["generated_at"],
    }
