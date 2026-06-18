"""小组出线概率模拟器.

赛制：2026 世界杯 12 组 × 4 队 = 48 队
- 每组前 2 名（共 24 队）直接晋级 32 强
- 8 个成绩最好的小组第 3 名（共 8 队）晋级 32 强
- 共 32 队进入淘汰赛

方法：蒙特卡洛 + Elo-Poisson（按 Poisson 分布随机采样比分）。
"""

import math
import random
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Match, Standing, Team
from app.services.elo_params import elo_to_lambda
from app.services.prediction import _predict_score_distribution


DIRECT_QUALIFIERS_PER_GROUP = 2
TOTAL_PLAYOFF_THIRD_PLACES = 8
SIMULATIONS = 5000


@dataclass
class TeamOdds:
    team_id: int
    team_name: str
    group_name: str
    flag_emoji: str
    points: int
    goal_diff: int
    goals_for: int
    direct_qualify_prob: float
    third_place_prob: float
    eliminated_prob: float
    advance_overall_prob: float  # 直接晋级 + 第 3 名


def _standings_snapshot(db: Session) -> dict[int, dict]:
    snapshot = {}
    for s in db.query(Standing).all():
        snapshot[s.team_id] = {
            "points": s.points or 0,
            "goal_diff": (s.goals_for or 0) - (s.goals_against or 0),
            "goals_for": s.goals_for or 0,
        }
    return snapshot


def _remaining_matches(db: Session) -> list[Match]:
    return (
        db.query(Match)
        .filter(Match.status != "finished")
        .filter(Match.stage == "小组赛")
        .filter(Match.home_team_id.isnot(None))
        .filter(Match.away_team_id.isnot(None))
        .all()
    )


def _poisson_sample(lam: float) -> int:
    """Knuth 算法采样 Poisson(lam)."""
    if lam <= 0:
        return 0
    import math
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p < L:
            return k - 1


def _simulate_match(match: Match) -> tuple[int, int]:
    """根据 Elo 模拟一场比赛的进球数."""
    h, a = match.home_team, match.away_team
    h_lam, a_lam = elo_to_lambda(h.elo_rating, a.elo_rating)
    # 限制 lam 上限避免极端值
    h_lam = min(h_lam, 5.0)
    a_lam = min(a_lam, 5.0)
    return _poisson_sample(h_lam), _poisson_sample(a_lam)


def simulate_group_advancement(db: Session, n_sims: int = SIMULATIONS) -> list[TeamOdds]:
    """运行蒙特卡洛模拟，返回每队出线概率列表.

    Args:
        n_sims: 模拟次数，默认 SIMULATIONS。总览等高频入口可传较小值以提速。
    """
    snapshot = _standings_snapshot(db)
    if not snapshot:
        return []

    teams = {t.id: t for t in db.query(Team).all()}
    remaining = _remaining_matches(db)

    counts = {tid: [0, 0, 0] for tid in snapshot}  # [direct, third, eliminated]

    for _ in range(n_sims):
        sim = {tid: dict(s) for tid, s in snapshot.items()}
        for m in remaining:
            hg, ag = _simulate_match(m)
            hid, aid = m.home_team_id, m.away_team_id
            if hid in sim and aid in sim:
                sim[hid]["goals_for"] += hg
                sim[aid]["goals_for"] += ag
                sim[hid]["goal_diff"] += hg - ag
                sim[aid]["goal_diff"] += ag - hg
                if hg > ag:
                    sim[hid]["points"] += 3
                elif hg == ag:
                    sim[hid]["points"] += 1
                    sim[aid]["points"] += 1
                else:
                    sim[aid]["points"] += 3

        # 按组排序
        group_ranking = defaultdict(list)
        for tid, stat in sim.items():
            t = teams.get(tid)
            if t:
                group_ranking[t.group_name].append((tid, stat))

        third_candidates = []
        for group_name, lst in group_ranking.items():
            lst.sort(key=lambda x: (-x[1]["points"], -x[1]["goal_diff"], -x[1]["goals_for"]))
            for rank, (tid, _) in enumerate(lst, start=1):
                if rank <= DIRECT_QUALIFIERS_PER_GROUP:
                    counts[tid][0] += 1
                elif rank == 3:
                    third_candidates.append((tid, lst[2][1]))
                else:
                    counts[tid][2] += 1

        # 最佳 8 个第 3 名
        third_candidates.sort(key=lambda x: (-x[1]["points"], -x[1]["goal_diff"], -x[1]["goals_for"]))
        qualifiers_3rd = {tid for tid, _ in third_candidates[:TOTAL_PLAYOFF_THIRD_PLACES]}
        for tid, _ in third_candidates:
            if tid in qualifiers_3rd:
                counts[tid][1] += 1
            else:
                counts[tid][2] += 1

    results = []
    for tid, (dq, tp, el) in counts.items():
        t = teams.get(tid)
        if not t:
            continue
        s = snapshot.get(tid, {})
        advance_overall = round((dq + tp) / n_sims * 100, 1)
        results.append(TeamOdds(
            team_id=tid,
            team_name=t.name_zh,
            group_name=t.group_name,
            flag_emoji=t.flag_emoji or "",
            points=s.get("points", 0),
            goal_diff=s.get("goal_diff", 0),
            goals_for=s.get("goals_for", 0),
            direct_qualify_prob=round(dq / n_sims * 100, 1),
            third_place_prob=round(tp / n_sims * 100, 1),
            eliminated_prob=round(el / n_sims * 100, 1),
            advance_overall_prob=advance_overall,
        ))
    results.sort(key=lambda x: (x.group_name, -x.points, -x.goal_diff, -x.goals_for))
    return results