"""v0.7.1 整届 2026 世界杯蒙特卡洛模拟.

设计要点 (详见 deliverables/v0.7.1_spec.md):
1. 预计算 48×48 pairwise 概率矩阵,MC 内层只查表 (避开 match_prob() 9x9 Poisson 循环)
2. 小组赛从 DB 真实 standings 起步,只模拟未完赛比赛
3. 淘汰赛 90 分钟 + 加时 + 点球 (按概率抽样)
4. R32 沿用 bracket_logic.R32_MATCHUPS + resolve_r32_matchups
5. R16/QF/SF/F 用标准二叉树推进 (89-104)
6. 性能目标: 10000 sims < 15s, 内存 < 50MB
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Match, MCRunHistory, Standing, Team
from app.services.bracket_logic import (
    R32_MATCHUPS,
    _assign_third_place_slots,
    resolve_r32_matchups,
    compute_group_standings,
    rank_third_place_teams,
)
from app.services.elo import HOME_BONUS, match_prob
from app.services.glicko2 import predict_outcome as g2_predict_outcome, lookup_glicko2_rating


# === 常量 ===
DIRECT_QUALIFIERS_PER_GROUP = 2
TOTAL_PLAYOFF_THIRD_PLACES = 8

# 加时 + 点球: 平局后两队近似 50/50
ET_PENS_SPLIT = 0.5

# 模拟次数上下界
MIN_SIMULATIONS = 100
MAX_SIMULATIONS = 50000
DEFAULT_SIMULATIONS = 10000


# === 数据类 ===
@dataclass
class _EloCache:
    """预读的 Elo 评分(每个 team_id → int)."""

    elo: Dict[int, int] = field(default_factory=dict)
    code: Dict[int, str] = field(default_factory=dict)


@dataclass
class _G2Cache:
    """预读的 Glicko-2 评分(每个 team_id → dict or None)."""

    ratings: Dict[int, Optional[dict]] = field(default_factory=dict)


@dataclass
class _GroupMatchLite:
    """MC 用的轻量级组赛比赛 (只存 ID + 比分, 引用 Team 通过 _teams)."""

    match_number: int
    home_team_id: int
    away_team_id: int
    is_finished: bool
    real_home_score: Optional[int] = None
    real_away_score: Optional[int] = None


@dataclass
class TournamentResult:
    """MC 输出."""

    n_sims: int
    model: str
    duration_seconds: float
    generated_at: str

    champion_distribution: Dict[str, float]  # code → prob
    finalist_distribution: Dict[str, float]
    semifinalist_distribution: Dict[str, float]
    quarterfinalist_distribution: Dict[str, float]
    r16_distribution: Dict[str, float]
    r32_distribution: Dict[str, float]
    group_advance_probability: Dict[str, Dict[str, float]]  # group → {code → prob}

    top_final_matchups: List[Dict]  # [{home, away, prob, count}, ...]
    top_semifinal_matchups: List[Dict]

    n_teams: int
    n_groups: int
    total_matches_per_sim: int


# === 预计算矩阵 ===
def _build_prob_matrix(
    db: Session,
    team_ids: List[int],
    model: str,
) -> Dict[Tuple[int, int], Dict[str, float]]:
    """为所有有序对 (home_id, away_id) 预计算 1X2 概率.

    Returns:
        {(home_id, away_id): {"home_win": float, "draw": float, "away_win": float}}
    """
    elo_cache, g2_cache = _build_elo_g2_caches(db, team_ids)

    matrix: Dict[Tuple[int, int], Dict[str, float]] = {}
    for h in team_ids:
        elo_h = elo_cache.elo.get(h)
        if elo_h is None:
            # 该队无 Elo 数据 → 均匀分布
            for a in team_ids:
                if a != h:
                    matrix[(h, a)] = {"home_win": 0.45, "draw": 0.22, "away_win": 0.33}
            continue
        g2_h = g2_cache.ratings.get(h)
        for a in team_ids:
            if a == h:
                continue
            elo_a = elo_cache.elo.get(a)
            if elo_a is None:
                matrix[(h, a)] = {"home_win": 0.55, "draw": 0.22, "away_win": 0.23}
                continue
            g2_a = g2_cache.ratings.get(a)

            # Elo Dixon-Coles
            elo_probs = match_prob(elo_h + HOME_BONUS, elo_a)
            elo_h_p = elo_probs["winA"]
            elo_d_p = elo_probs["draw"]
            elo_a_p = elo_probs["winB"]

            if model == "elo":
                matrix[(h, a)] = {
                    "home_win": round(elo_h_p, 4),
                    "draw": round(elo_d_p, 4),
                    "away_win": round(elo_a_p, 4),
                }
                continue

            # Glicko-2
            if g2_h and g2_a:
                g2_probs = g2_predict_outcome(
                    g2_h["rating"] + HOME_BONUS, g2_h["rd"],
                    g2_a["rating"], g2_a["rd"],
                )
                g2_h_p = g2_probs["win_a"]
                g2_d_p = g2_probs["draw"]
                g2_a_p = g2_probs["win_b"]
            else:
                # 缺 G2 数据 → blend 退化为纯 Elo
                g2_h_p, g2_d_p, g2_a_p = elo_h_p, elo_d_p, elo_a_p

            if model == "glicko2":
                matrix[(h, a)] = {
                    "home_win": round(g2_h_p, 4),
                    "draw": round(g2_d_p, 4),
                    "away_win": round(g2_a_p, 4),
                }
            else:  # blend
                matrix[(h, a)] = {
                    "home_win": round(0.5 * elo_h_p + 0.5 * g2_h_p, 4),
                    "draw": round(0.5 * elo_d_p + 0.5 * g2_d_p, 4),
                    "away_win": round(0.5 * elo_a_p + 0.5 * g2_a_p, 4),
                }
    return matrix


def _build_elo_g2_caches(db: Session, team_ids: List[int]) -> Tuple[_EloCache, _G2Cache]:
    """预读全部 team 的 Elo + G2 rating 进内存."""
    elo_cache = _EloCache()
    g2_cache = _G2Cache()
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    for tid in team_ids:
        t = teams.get(tid)
        if not t:
            continue
        elo_cache.code[tid] = t.fifa_code
        elo_cache.elo[tid] = t.elo_rating or 1500
        # G2: 用 fifa_code 查
        g2_rating = lookup_glicko2_rating(t.fifa_code)
        g2_cache.ratings[tid] = g2_rating
    return elo_cache, g2_cache


# === 组赛模拟 ===
def _poisson_sample(lam: float, rng: random.Random) -> int:
    """Knuth 算法 Poisson(lam)."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p < L:
            return k - 1


def _elo_to_lambda(home_elo: float, away_elo: float) -> Tuple[float, float]:
    """Elo → 期望进球 lambda (简化复刻 v0.3.0 逻辑)."""
    # 与 prediction.py 保持一致: HOME_ADVANTAGE=80, BASE_LAMBDA=1.3
    HOME_ADVANTAGE = 80
    BASE_LAMBDA = 1.3
    GOAL_PER_ELO_DIFF = 0.005
    diff = home_elo - away_elo + HOME_ADVANTAGE
    h_lam = max(0.3, BASE_LAMBDA + diff * GOAL_PER_ELO_DIFF)
    a_lam = max(0.3, BASE_LAMBDA - diff * GOAL_PER_ELO_DIFF)
    return h_lam, a_lam


def _load_group_matches(db: Session) -> List[_GroupMatchLite]:
    """载入所有小组赛比赛 + 已完赛比分."""
    out = []
    for m in db.query(Match).filter(
        Match.match_number <= 72,
        Match.home_team_id.isnot(None),
        Match.away_team_id.isnot(None),
    ).all():
        out.append(_GroupMatchLite(
            match_number=m.match_number,
            home_team_id=m.home_team_id,
            away_team_id=m.away_team_id,
            is_finished=(m.status == "finished" and m.home_score is not None),
            real_home_score=m.home_score,
            real_away_score=m.away_score,
        ))
    return out


def _simulate_group_stage(
    group_matches: List[_GroupMatchLite],
    elo_cache: _EloCache,
    rng: random.Random,
) -> Dict[int, Dict[str, int]]:
    """模拟一场完整的组赛 (1 个 sim), 返回每队 {points, gf, ga, gd}.

    已完赛比赛直接套用真实比分;未完赛用 Poisson 模拟。
    """
    table: Dict[int, Dict[str, int]] = defaultdict(
        lambda: {"points": 0, "gf": 0, "ga": 0, "gd": 0, "played": 0}
    )

    # 先收集参赛队
    for m in group_matches:
        table[m.home_team_id]  # trigger defaultdict init
        table[m.away_team_id]

    for m in group_matches:
        h, a = m.home_team_id, m.away_team_id
        if m.is_finished:
            hg, ag = m.real_home_score, m.real_away_score
        else:
            elo_h = elo_cache.elo.get(h, 1500)
            elo_a = elo_cache.elo.get(a, 1500)
            h_lam, a_lam = _elo_to_lambda(elo_h, elo_a)
            h_lam = min(h_lam, 5.0)
            a_lam = min(a_lam, 5.0)
            hg = _poisson_sample(h_lam, rng)
            ag = _poisson_sample(a_lam, rng)

        table[h]["gf"] += hg
        table[h]["ga"] += ag
        table[h]["gd"] += hg - ag
        table[a]["gf"] += ag
        table[a]["ga"] += hg
        table[a]["gd"] += ag - hg
        table[h]["played"] += 1
        table[a]["played"] += 1

        if hg > ag:
            table[h]["points"] += 3
        elif hg == ag:
            table[h]["points"] += 1
            table[a]["points"] += 1
        else:
            table[a]["points"] += 3

    return dict(table)


def _select_qualified(
    flat_table: Dict[int, Dict[str, int]],
    teams: Dict[int, Team],
) -> List[int]:
    """按组排名 + 最佳 8 个第三, 返回 32 强 team_id 列表.

    Args:
        flat_table: team_id → {points, gf, ga, gd, played}  (来自 _simulate_group_stage)
        teams: team_id → Team ORM
    """
    # 先按 group_name 聚合
    grouped: Dict[str, Dict[int, Dict[str, int]]] = {}
    for tid, stat in flat_table.items():
        t = teams.get(tid)
        if t is None or not t.group_name:
            continue
        grouped.setdefault(t.group_name, {})[tid] = stat

    direct: List[int] = []
    thirds: List[Tuple[int, Dict[str, int]]] = []

    for group_name, tbl in grouped.items():
        # 按 points > gd > gf 降序
        rows = sorted(
            tbl.items(),
            key=lambda kv: (kv[1]["points"], kv[1]["gd"], kv[1]["gf"]),
            reverse=True,
        )
        if len(rows) >= 1:
            direct.append(rows[0][0])
        if len(rows) >= 2:
            direct.append(rows[1][0])
        if len(rows) >= 3:
            thirds.append((rows[2][0], rows[2][1]))

    thirds.sort(
        key=lambda x: (x[1]["points"], x[1]["gd"], x[1]["gf"]),
        reverse=True,
    )
    for tid, _ in thirds[:TOTAL_PLAYOFF_THIRD_PLACES]:
        direct.append(tid)

    return direct


# === 淘汰赛模拟 ===
def _knockout_winner(
    probs: Dict[str, float],
    home_id: int,
    away_id: int,
    rng: random.Random,
) -> int:
    """淘汰赛 90 分钟 + 加时 + 点球."""
    h, d, a = probs["home_win"], probs["draw"], probs["away_win"]
    r = rng.random()
    if r < h:
        return home_id
    if r < h + d:
        # 加时 + 点球近似 50/50
        return home_id if rng.random() < ET_PENS_SPLIT else away_id
    return away_id


# === 主入口 ===
def simulate_full_tournament(
    db: Session,
    n_sims: int = DEFAULT_SIMULATIONS,
    model: str = "blend",
    return_top_n: int = 8,
    seed: Optional[int] = None,
) -> TournamentResult:
    """运行整届 2026 世界杯蒙特卡洛.

    Args:
        db: SQLAlchemy session
        n_sims: 模拟次数, 范围 [100, 50000]
        model: 'blend' | 'elo' | 'glicko2'
        return_top_n: top N 对阵频率
        seed: 随机种子 (可重现)
    """
    if model not in ("blend", "elo", "glicko2"):
        raise ValueError(f"model 必须是 blend/elo/glicko2, 收到 {model!r}")
    if n_sims < MIN_SIMULATIONS or n_sims > MAX_SIMULATIONS:
        raise ValueError(
            f"n_sims 必须在 [{MIN_SIMULATIONS}, {MAX_SIMULATIONS}], 收到 {n_sims}"
        )

    rng = random.Random(seed)

    t_start = time.time()

    # 1) 加载所有 team (限 48 强)
    teams = {t.id: t for t in db.query(Team).all()}
    team_ids = list(teams.keys())
    if not team_ids:
        raise ValueError("DB 中无球队数据")

    # 2) 预读组赛 + 预计算 prob_matrix
    group_matches = _load_group_matches(db)
    if not group_matches:
        raise ValueError("DB 中无小组赛比赛 (match_number 1-72)")

    elo_cache, g2_cache = _build_elo_g2_caches(db, team_ids)
    prob_matrix = _build_prob_matrix(db, team_ids, model)

    # 3) 解析 R32 槽位 (沿用 bracket_logic)
    # 注: 这里要传一个模拟后的 standings 给 resolve_r32_matchups.
    # 但 MC 每 sim 的 standings 不同, 所以 R32 解析放到 _simulate_knockout_round 内.

    # 4) 主循环
    counters: Dict[int, Counter] = {
        tid: Counter() for tid in team_ids
    }
    # 额外: 决赛/半决赛 对阵统计
    final_matchup_counter: Counter = Counter()
    sf_matchup_counter: Counter = Counter()

    for sim_idx in range(n_sims):
        # 4a) 模拟组赛
        group_tables = _simulate_group_stage(group_matches, elo_cache, rng)

        # 4b) 选 32 强
        r32_team_ids = _select_qualified(group_tables, teams)
        for tid in r32_team_ids:
            counters[tid]["group_advance"] += 1
        r32_qualifiers = set(r32_team_ids)

        # 4c) R32 (按 R32_MATCHUPS 顺序)
        # 用 bracket_logic 的 8 队第三分配算法,避免 A3 同时被多槽位选中
        r32_team_slots = _resolve_r32_slots_for_sim(group_tables, teams)
        r32_winners: List[int] = []
        for slot_def in r32_team_slots:
            home_id, away_id = slot_def["home_id"], slot_def["away_id"]
            if home_id is None or away_id is None:
                continue
            if home_id == away_id:
                continue
            w = _knockout_winner(
                prob_matrix[(home_id, away_id)], home_id, away_id, rng
            )
            r32_winners.append(w)
            if w == home_id:
                counters[away_id]["r32"] += 1
            else:
                counters[home_id]["r32"] += 1

        # 4d) R16 → QF → SF → F (二叉树)
        r16_winners, r16_losers = _advance_round(
            r32_winners, prob_matrix, rng
        )
        for tid in r16_losers:
            counters[tid]["r16"] += 1

        qf_winners, qf_losers = _advance_round(
            r16_winners, prob_matrix, rng
        )
        for tid in qf_losers:
            counters[tid]["qf"] += 1

        sf_winners, sf_losers = _advance_round(
            qf_winners, prob_matrix, rng
        )
        for tid in sf_losers:
            counters[tid]["sf"] += 1

        # 决赛
        if len(sf_winners) == 2:
            f_home, f_away = sf_winners[0], sf_winners[1]
            f_winner = _knockout_winner(
                prob_matrix[(f_home, f_away)], f_home, f_away, rng
            )
            f_loser = f_away if f_winner == f_home else f_home
            counters[f_winner]["champion"] += 1
            # finalist = reached F (两支决赛队都算)
            counters[f_home]["finalist"] += 1
            counters[f_away]["finalist"] += 1
            # f_loser 输 F (没新加 counter, 由 finalist - champion 推得)

            # 记录决赛对 (用 code 排序, 避免 home/away 顺序噪声)
            f_matchup = tuple(sorted(
                [elo_cache.code.get(f_home, "?"), elo_cache.code.get(f_away, "?")]
            ))
            final_matchup_counter[f_matchup] += 1

            # 半决赛对 (4 队 2 场)
            sf_matchup = tuple(sorted([
                elo_cache.code.get(sf_winners[0], "?"),
                elo_cache.code.get(sf_winners[1], "?"),
            ]))
            sf_matchup_counter[sf_matchup] += 1
        else:
            # 异常兜底: 跳过本次决赛
            for tid in sf_winners:
                counters[tid]["sf"] += 1

    # 5) 归一化
    duration = time.time() - t_start
    from datetime import datetime, timezone

    # API 字段语义: "P(到达这一轮)" (reached this round)
    # - group_advance = P(从组赛出线) = P(进入 R32)
    # - r32 = P(进入 R32) = group_advance
    # - r16 = P(进入 R16) = P(赢得 R32) = group_advance - r32_exit
    # - qf  = P(进入 QF)  = r16 - r16_exit
    # - sf  = P(进入 SF)  = qf  - qf_exit
    # - finalist = P(进入 F) = sf - sf_exit = 直接累计决赛两队
    # - champion = P(夺冠)
    #
    # 这里 counters 里的 "r32" = lost in R32 (退出 R32), "r16" = lost in R16, etc.
    # "finalist" = reached F (两支决赛队都 +1)
    # "champion" = won F

    def _exit_count(round_exit: str) -> Dict[str, int]:
        """每队的退出数."""
        return {
            elo_cache.code.get(tid, f"team_{tid}"): c.get(round_exit, 0)
            for tid, c in counters.items()
        }

    def _reached_prob(reached: str) -> Dict[str, float]:
        """每队到达某轮的概率. 自然单调: group_advance >= r32 >= r16 >= qf >= sf >= finalist >= champion."""
        ga = _exit_count("group_advance")
        e_r32 = _exit_count("r32")
        e_r16 = _exit_count("r16")
        e_qf = _exit_count("qf")
        e_sf = _exit_count("sf")
        f_count = _exit_count("finalist")
        c = _exit_count("champion")

        d: Dict[str, float] = {}
        for code in ga:
            gv = ga[code]
            if reached == "group_advance":
                p = gv
            elif reached == "r32":
                p = gv  # 到达 R32 = 出线
            elif reached == "r16":
                p = max(0, gv - e_r32[code])
            elif reached == "qf":
                p = max(0, gv - e_r32[code] - e_r16[code])
            elif reached == "sf":
                p = max(0, gv - e_r32[code] - e_r16[code] - e_qf[code])
            elif reached == "finalist":
                p = f_count[code]  # 直接累计
            elif reached == "champion":
                p = c[code]
            else:
                p = 0
            d[code] = round(p / n_sims, 4)
        return dict(sorted(d.items(), key=lambda x: -x[1]))

    # group_advance 按 group 聚合
    groups = sorted({teams[tid].group_name for tid in team_ids if teams[tid].group_name})
    group_advance: Dict[str, Dict[str, float]] = {}
    for g in groups:
        inner: Dict[str, float] = {}
        for tid, t in teams.items():
            if t.group_name != g:
                continue
            inner[t.fifa_code] = round(
                counters[tid].get("group_advance", 0) / n_sims, 4
            )
        # 按 prob 降序
        group_advance[g] = dict(sorted(inner.items(), key=lambda x: -x[1]))

    # Top N 对阵
    def _top_n(counter: Counter, n: int) -> List[Dict]:
        top = counter.most_common(n)
        return [
            {"home": h, "away": a, "prob": round(c / n_sims, 4), "count": c}
            for (h, a), c in top
        ]

    # 统计 group 数
    n_groups = len(groups)
    n_teams = len(team_ids)

    return TournamentResult(
        n_sims=n_sims,
        model=model,
        duration_seconds=round(duration, 2),
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        champion_distribution=_reached_prob("champion"),
        finalist_distribution=_reached_prob("finalist"),
        semifinalist_distribution=_reached_prob("sf"),
        quarterfinalist_distribution=_reached_prob("qf"),
        r16_distribution=_reached_prob("r16"),
        r32_distribution=_reached_prob("r32"),
        group_advance_probability=group_advance,
        top_final_matchups=_top_n(final_matchup_counter, return_top_n),
        top_semifinal_matchups=_top_n(sf_matchup_counter, return_top_n),
        n_teams=n_teams,
        n_groups=n_groups,
        total_matches_per_sim=len(group_matches) + 31,  # 72 + 31 = 103
    )


def _advance_round(
    winners: List[int],
    prob_matrix: Dict[Tuple[int, int], Dict[str, float]],
    rng: random.Random,
) -> Tuple[List[int], List[int]]:
    """把胜者按 [0,1], [2,3], [4,5]... 配对推进一轮. 返回 (新胜者, 失败者).

    防御: 如果 h == a (异常状态,例如前一轮有 skip), 直接让 h 晋级,a 算失败。
    """
    new_winners: List[int] = []
    losers: List[int] = []
    for i in range(0, len(winners) - 1, 2):
        h, a = winners[i], winners[i + 1]
        if h == a:
            # 防御: 同队配对, 让 h 晋级
            new_winners.append(h)
            losers.append(a)
            continue
        w = _knockout_winner(prob_matrix[(h, a)], h, a, rng)
        l = a if w == h else h
        new_winners.append(w)
        losers.append(l)
    # 若奇数个, 最后一个直接晋级 (不应发生, R32=16, R16=8, QF=4, SF=2)
    if len(winners) % 2 == 1:
        new_winners.append(winners[-1])
    return new_winners, losers


def _resolve_r32_slots_for_sim(
    flat_table: Dict[int, Dict[str, int]],
    teams: Dict[int, Team],
) -> List[Dict[str, Optional[int]]]:
    """解析 R32 16 个槽位,返回 [{home_id, away_id}, ...].

    关键: 复用 bracket_logic._assign_third_place_slots 的贪心分配算法,
    避免同一支第 3 名队伍被多个 3XXX 槽位重复选中。
    """
    # 1) 按 group 聚合 standings (供 _1/_2 解析)
    grouped: Dict[str, List[Tuple[int, Dict[str, int]]]] = {}
    for tid, stat in flat_table.items():
        t = teams.get(tid)
        if t is None or not t.group_name:
            continue
        grouped.setdefault(t.group_name, []).append((tid, stat))
    for g in grouped:
        grouped[g].sort(
            key=lambda kv: (kv[1]["points"], kv[1]["gd"], kv[1]["gf"]),
            reverse=True,
        )

    # 2) 取 8 个最佳第 3 名 (按 points/gd/gf 排名)
    thirds_flat: List[Tuple[int, str, Dict[str, int]]] = []
    for g, rows in grouped.items():
        if len(rows) >= 3:
            tid, stat = rows[2]
            thirds_flat.append((tid, g, stat))
    thirds_flat.sort(
        key=lambda x: (x[2]["points"], x[2]["gd"], x[2]["gf"]),
        reverse=True,
    )
    top_8_thirds = thirds_flat[:TOTAL_PLAYOFF_THIRD_PLACES]

    # 3) 复用 bracket_logic 的贪心分配
    # 构造 StandingRow-like 对象
    class _StubTeam:
        def __init__(self, group_name: str):
            self.group_name = group_name
    class _StubRow:
        def __init__(self, group_name: str):
            self.team = _StubTeam(group_name)
    stub_thirds = [_StubRow(g) for (_, g, _) in top_8_thirds]
    assigned_thirds_map = _assign_third_place_slots(stub_thirds)
    # assigned_thirds_map: slot_source ('3ABCDF') → group_name

    # 4) 解析每个 R32 槽位
    out: List[Dict[str, Optional[int]]] = []
    for m in R32_MATCHUPS:
        home_source = m["home"]
        away_source = m["away"]

        def _resolve_1_or_2(source: str) -> Optional[int]:
            rank = int(source[0]) - 1
            g = source[1:]
            rows = grouped.get(g, [])
            if len(rows) > rank:
                return rows[rank][0]
            return None

        if home_source.startswith("3"):
            g = assigned_thirds_map.get(home_source)
            home_id = None
            if g:
                rows = grouped.get(g, [])
                if len(rows) >= 3:
                    home_id = rows[2][0]
        else:
            home_id = _resolve_1_or_2(home_source)

        if away_source.startswith("3"):
            g = assigned_thirds_map.get(away_source)
            away_id = None
            if g:
                rows = grouped.get(g, [])
                if len(rows) >= 3:
                    away_id = rows[2][0]
        else:
            away_id = _resolve_1_or_2(away_source)

        out.append({"home_id": home_id, "away_id": away_id})
    return out


def tournament_result_to_dict(result: TournamentResult) -> Dict:
    """TournamentResult → API JSON."""
    return {
        "n_sims": result.n_sims,
        "model": result.model,
        "duration_seconds": result.duration_seconds,
        "generated_at": result.generated_at,
        "champion_distribution": result.champion_distribution,
        "finalist_distribution": result.finalist_distribution,
        "semifinalist_distribution": result.semifinalist_distribution,
        "quarterfinalist_distribution": result.quarterfinalist_distribution,
        "r16_distribution": result.r16_distribution,
        "r32_distribution": result.r32_distribution,
        "group_advance_probability": result.group_advance_probability,
        "top_final_matchups": result.top_final_matchups,
        "top_semifinal_matchups": result.top_semifinal_matchups,
        "n_teams": result.n_teams,
        "n_groups": result.n_groups,
        "total_matches_per_sim": result.total_matches_per_sim,
    }


# === v0.7.1.1 缓存层 ===
MC_CACHE_TTL_SECONDS = 6 * 3600  # 6h


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_mc_cache(
    db: Session,
    model: str,
    n_sims: int,
    seed: int,
    ttl_seconds: int = MC_CACHE_TTL_SECONDS,
) -> Optional[Dict]:
    """查询有效 MC 缓存.

    Returns:
        命中且未过期时返回 API dict;否则 None。
    """
    row = (
        db.query(MCRunHistory)
        .filter(MCRunHistory.model == model)
        .filter(MCRunHistory.n_sims == n_sims)
        .filter(MCRunHistory.seed == seed)
        .order_by(MCRunHistory.generated_at.desc())
        .first()
    )
    if row is None:
        return None

    # SQLite 存的是 naive UTC;统一按 UTC 比较
    generated = row.generated_at
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)

    age_seconds = (_now_utc() - generated).total_seconds()
    if age_seconds > ttl_seconds:
        return None

    return {
        "n_sims": row.n_sims,
        "model": row.model,
        "duration_seconds": row.duration_seconds,
        "generated_at": generated.isoformat(),
        "champion_distribution": json.loads(row.champion_distribution),
        "finalist_distribution": json.loads(row.finalist_distribution),
        "semifinalist_distribution": json.loads(row.semifinalist_distribution),
        "quarterfinalist_distribution": json.loads(row.quarterfinalist_distribution),
        "r16_distribution": json.loads(row.r16_distribution),
        "r32_distribution": json.loads(row.r32_distribution),
        "group_advance_probability": json.loads(row.group_advance_probability),
        "top_final_matchups": json.loads(row.top_final_matchups),
        "top_semifinal_matchups": json.loads(row.top_semifinal_matchups),
        "n_teams": row.n_teams,
        "n_groups": row.n_groups,
        "total_matches_per_sim": row.total_matches_per_sim,
        "cached": True,
        "cache_age_seconds": age_seconds,
    }


def save_mc_cache(
    db: Session,
    model: str,
    n_sims: int,
    seed: int,
    result: TournamentResult,
) -> MCRunHistory:
    """把 TournamentResult 写入 mc_run_history,同 (model,n_sims,seed) 覆盖旧记录."""
    # 删除同键旧记录,保持表精简
    db.query(MCRunHistory).filter(
        MCRunHistory.model == model,
        MCRunHistory.n_sims == n_sims,
        MCRunHistory.seed == seed,
    ).delete(synchronize_session=False)

    row = MCRunHistory(
        model=model,
        n_sims=n_sims,
        seed=seed,
        generated_at=_now_utc(),
        duration_seconds=result.duration_seconds,
        champion_distribution=json.dumps(result.champion_distribution),
        finalist_distribution=json.dumps(result.finalist_distribution),
        semifinalist_distribution=json.dumps(result.semifinalist_distribution),
        quarterfinalist_distribution=json.dumps(result.quarterfinalist_distribution),
        r16_distribution=json.dumps(result.r16_distribution),
        r32_distribution=json.dumps(result.r32_distribution),
        group_advance_probability=json.dumps(result.group_advance_probability),
        top_final_matchups=json.dumps(result.top_final_matchups),
        top_semifinal_matchups=json.dumps(result.top_semifinal_matchups),
        n_teams=result.n_teams,
        n_groups=result.n_groups,
        total_matches_per_sim=result.total_matches_per_sim,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def run_mc_with_cache(
    db: Session,
    n_sims: int,
    model: str,
    return_top_n: int,
    seed: int,
    refresh: bool = False,
) -> Dict:
    """缓存优先入口.命中则秒回;否则计算并写缓存."""
    if not refresh:
        cached = load_mc_cache(db, model=model, n_sims=n_sims, seed=seed)
        if cached is not None:
            return cached

    result = simulate_full_tournament(
        db,
        n_sims=n_sims,
        model=model,
        return_top_n=return_top_n,
        seed=seed,
    )
    save_mc_cache(db, model=model, n_sims=n_sims, seed=seed, result=result)
    return tournament_result_to_dict(result)
