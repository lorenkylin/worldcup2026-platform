"""Elo-Poisson v1 预测服务.

核心逻辑：
1. B1 — FIFA 排名 → Elo 校准：对数曲线映射（业内常用），让排名 1 = ~2100、排名 50 = ~1880。
2. Elo 分差 + 中立场地优势 → 两队期望进球 λ。
3. B2 — 近期状态因子：最近 5 场积分差（0-15）作为 λ 的 ±10% 微调。
4. Poisson 矩阵 → 胜平负概率、推荐比分、星级。
5. B3 — 历史交锋（H2H）：从已完成的两队历史比赛统计胜平负，写进理由。
6. 3-5 条可解释理由。
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Team, Match, MatchEvent, H2HHistoricalMatch
from app.schemas import PredictionOut
from app.services.h2h_backfill import query_h2h_history


# =============== B1：FIFA 排名 → Elo 校准 ===============
# 业内常用的对数曲线映射公式：
#   Elo = 2200 - 100 * log10(rank)
# 这样：
#   rank 1  → 2200（理论上界）
#   rank 5  → 2170
#   rank 10 → 2150
#   rank 20 → 2126
#   rank 50 → 2080
#   rank 100 → 2050
# 但实际公开 Elo 区间约 1500-2200，我们希望分布在 1500-2050 区间以让 λ 合理：
#   采用 Elo = 2200 - 200 * log10(rank)
#   rank 1 → 2200（但会被 2200 上限夹断 → 2050）
#   rank 5 → 2140
#   rank 10 → 2100
#   rank 50 → 1960
#   rank 100 → 1900
#   rank 200 → 1840
#   无排名（200+）→ 1800
#
# 考虑到赛事模型对排名 1-10 之间需要更显著的区分（强队 vs 中上游），
# 微调：Elo = 2200 - 230 * log10(rank)，让前 10 名拉开。
#   rank 1 → 2200（截断 2050）
#   rank 5 → 2138
#   rank 10 → 2099
#   rank 20 → 2074
#   rank 50 → 2006
#   rank 100 → 1944
#   rank 200 → 1882
# 无排名 → 1750（兜底，对应 ≈ rank 280）

FALLBACK_ELO_NO_RANK = 1750
ELO_MAX_CAP = 2050


def elo_from_fifa_rank(rank: Optional[int]) -> int:
    """B1: 把 FIFA 排名映射为 Elo 评分（对数曲线 + 上下限）。"""
    if rank is None or rank <= 0:
        return FALLBACK_ELO_NO_RANK
    raw = 2200 - 230 * math.log10(rank)
    return int(round(min(ELO_MAX_CAP, max(1500, raw))))


# =============== 基础预测参数 ===============
HOME_ADVANTAGE = 60.0  # 中立场地优势（世界杯是中性，但模拟赛仍有微调）
GOAL_PER_ELO_DIFF = 0.0035
BASE_LAMBDA = 1.35
MAX_STARS = 5

# B2: 近期状态因子系数（±10% λ 调整）
RECENT_FORM_WEIGHT = 0.10
RECENT_FORM_MAX = 15  # 5 场全胜 5*3=15


def _elo_to_lambda(home_elo: float, away_elo: float) -> tuple[float, float]:
    """将 Elo 分差转换为两队期望进球（中性 + 主场优势）。"""
    diff = home_elo - away_elo + HOME_ADVANTAGE
    home_lambda = BASE_LAMBDA + diff * GOAL_PER_ELO_DIFF
    away_lambda = BASE_LAMBDA - diff * GOAL_PER_ELO_DIFF
    return max(0.3, home_lambda), max(0.3, away_lambda)


def _apply_recent_form(
    home_lambda: float,
    away_lambda: float,
    home_form: Optional[int],
    away_form: Optional[int],
) -> Tuple[float, float]:
    """B2: 根据两队最近 5 场积分差，对 λ 做 ±10% 微调。

    form 范围 0-15（每场胜 3 平 1 负 0），归一化到 [-1, 1] 后乘以权重。
    主场队伍 form 越好，home_lambda 上调、away_lambda 下调。
    """
    if home_form is None or away_form is None:
        return home_lambda, away_lambda

    # 归一化到 [-1, 1]
    home_norm = max(-1.0, min(1.0, (home_form - RECENT_FORM_MAX / 2) / (RECENT_FORM_MAX / 2)))
    away_norm = max(-1.0, min(1.0, (away_form - RECENT_FORM_MAX / 2) / (RECENT_FORM_MAX / 2)))

    # 净 form 优势 = 主场队 form 优势 - 客场队 form 优势
    net_advantage = (home_norm - away_norm) / 2  # 归到 [-1, 1]

    home_lambda *= 1 + net_advantage * RECENT_FORM_WEIGHT
    away_lambda *= 1 - net_advantage * RECENT_FORM_WEIGHT

    return max(0.3, home_lambda), max(0.3, away_lambda)


def _poisson_prob(lam: float, k: int) -> float:
    """计算 Poisson(lam) 取 k 的概率."""
    if k < 0:
        return 0.0
    return (lam**k) * math.exp(-lam) / math.factorial(k)


def _predict_score_distribution(home_lambda: float, away_lambda: float, max_goals: int = 7):
    """计算比分分布矩阵与胜负平概率."""
    home_probs = [_poisson_prob(home_lambda, g) for g in range(max_goals + 1)]
    away_probs = [_poisson_prob(away_lambda, g) for g in range(max_goals + 1)]

    home_win = draw = away_win = 0.0
    best_prob = 0.0
    best_score = "0:0"

    for i, hp in enumerate(home_probs):
        for j, ap in enumerate(away_probs):
            p = hp * ap
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p
            if p > best_prob:
                best_prob = p
                best_score = f"{i}:{j}"

    return home_win, draw, away_win, best_score


def _stars(home_win: float, draw: float, away_win: float) -> int:
    """根据最可能结果的置信度给出 1-5 星."""
    top = max(home_win, draw, away_win)
    stars = min(MAX_STARS, max(1, int((top - 0.30) * 25)))
    return stars


def _query_h2h(db: Optional[Session], home: Team, away: Team, lookback: int = 5) -> dict:
    """B3: 查询两队历史交锋记录.

    返回：
        {
            "home_wins": 主队胜场数（按 home_team 视角）,
            "away_wins": 客队胜场数,
            "draws": 平局数,
            "sample": 比赛样本数,
            "summary": "近 N 次交锋 X 胜 Y 平 Z 负",
        }
    """
    result = {"home_wins": 0, "away_wins": 0, "draws": 0, "sample": 0, "summary": "", "source": "current"}
    if db is None:
        return result

    # 1. 优先查 2026 已完赛比赛（更相关）
    past_matches = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
            (
                (
                    (Match.home_team_id == home.id)
                    & (Match.away_team_id == away.id)
                )
                | (
                    (Match.home_team_id == away.id)
                    & (Match.away_team_id == home.id)
                )
            ),
        )
        .order_by(Match.kickoff_at.desc())
        .limit(lookback)
        .all()
    )

    home_wins = 0
    away_wins = 0
    draws = 0
    sample = 0
    source = ""

    if past_matches:
        # 2026 完赛 → 用作 H2H
        sample = len(past_matches)
        for m in past_matches:
            # 归一到"home 视角"（不区分场地）
            home_goals = m.home_score if m.home_team_id == home.id else m.away_score
            away_goals = m.away_score if m.home_team_id == home.id else m.home_score
            if home_goals > away_goals:
                home_wins += 1
            elif home_goals < away_goals:
                away_wins += 1
            else:
                draws += 1
        source = "current"
    else:
        # 2. 回退到 2018/2022 世界杯种子数据
        hist = query_h2h_history(db, home.fifa_code, away.fifa_code, lookback=lookback)
        if hist:
            sample = len(hist)
            for h in hist:
                # 归一到 home 视角
                if h.home_fifa_code == home.fifa_code:
                    hg, ag = h.home_score, h.away_score
                else:
                    hg, ag = h.away_score, h.home_score
                if hg > ag:
                    home_wins += 1
                elif hg < ag:
                    away_wins += 1
                else:
                    draws += 1
            source = "history"

    if sample == 0:
        return result

    result["home_wins"] = home_wins
    result["away_wins"] = away_wins
    result["draws"] = draws
    result["sample"] = sample
    result["source"] = source
    suffix = "（历史交锋）" if source == "history" else ""
    result["summary"] = (
        f"近 {sample} 次交锋 {home.name_zh}{home_wins}胜{draws}平{away_wins}负{suffix}"
    )
    return result


def _form_string(form_points: Optional[int]) -> Optional[str]:
    """把 0-15 积分转换成 5 字符形态字符串（如 WWDWL）。仅在没有完整记录时返回 None。"""
    if form_points is None:
        return None
    # 由于仅有点数无法反推 W/D/L 序列，这里用概览代替："近 5 场 X 分"
    return f"近 5 场 {form_points} 分"


def _factors_breakdown(
    home: Team,
    away: Team,
    home_lambda: float,
    away_lambda: float,
    home_form: Optional[int],
    away_form: Optional[int],
    h2h: dict,
) -> dict:
    """F2: 拆分各因子对最终胜率的贡献，供前端可解释性面板展示.

    Returns:
        {
            "elo": {  # B1 因子
                "home_elo": 2050,
                "away_elo": 1950,
                "diff": 100,
                "home_advantage": 60,
                "contribution_to_lambda": 0.42,  # 主场相对客场的 λ 优势
            },
            "form": {  # B2 因子
                "home_points": 12,
                "away_points": 6,
                "diff": 6,
                "applied": true,  # 是否有 form 数据
                "weight": 0.10,
            },
            "h2h": {  # B3 因子
                "sample": 3,
                "home_wins": 2,
                "away_wins": 1,
                "draws": 0,
                "source": "current" | "history" | "none",
            },
            "lambda": {  # 模型参数
                "home": 1.5,
                "away": 1.2,
                "base": 1.35,
            },
        }
    """
    elo_diff = home.elo_rating - away.elo_rating
    elo_diff_with_advantage = elo_diff + HOME_ADVANTAGE
    lambda_advantage = elo_diff_with_advantage * GOAL_PER_ELO_DIFF

    return {
        "elo": {
            "home_elo": home.elo_rating,
            "away_elo": away.elo_rating,
            "diff": elo_diff,
            "home_advantage": int(HOME_ADVANTAGE),
            "contribution_to_lambda": round(lambda_advantage, 3),
        },
        "form": {
            "home_points": home_form,
            "away_points": away_form,
            "diff": (home_form - away_form) if (home_form is not None and away_form is not None) else None,
            "applied": home_form is not None and away_form is not None,
            "weight": RECENT_FORM_WEIGHT,
        },
        "h2h": {
            "sample": h2h.get("sample", 0),
            "home_wins": h2h.get("home_wins", 0),
            "away_wins": h2h.get("away_wins", 0),
            "draws": h2h.get("draws", 0),
            "source": h2h.get("source", "none"),
        },
        "lambda": {
            "home": round(home_lambda, 3),
            "away": round(away_lambda, 3),
            "base": BASE_LAMBDA,
        },
    }


def _reasons(
    home: Team,
    away: Team,
    home_lambda: float,
    away_lambda: float,
    home_win: float,
    home_form: Optional[int],
    away_form: Optional[int],
    h2h: dict,
) -> List[str]:
    """生成 3-5 条可解释理由."""
    reasons: List[str] = []
    elo_diff = home.elo_rating - away.elo_rating
    rank_diff = (home.fifa_rank or 999) - (away.fifa_rank or 999)

    # 1) Elo / FIFA 排名
    if abs(elo_diff) >= 80:
        leader = home if elo_diff > 0 else away
        reasons.append(
            f"{leader.name_zh} Elo 积分领先 {abs(elo_diff):.0f} 分，纸面实力占优。"
        )
    elif rank_diff <= -20:
        reasons.append(
            f"{home.name_zh} FIFA 排名更靠前（{home.fifa_rank} vs {away.fifa_rank}）。"
        )
    elif rank_diff >= 20:
        reasons.append(
            f"{away.name_zh} FIFA 排名更靠前（{away.fifa_rank} vs {home.fifa_rank}）。"
        )
    else:
        reasons.append("两队 Elo 积分接近，实力在伯仲之间，胜负取决于临场发挥。")

    # 2) λ 比较
    if home_lambda > away_lambda + 0.4:
        reasons.append(
            f"模型预计 {home.name_zh} 进攻效率更高（场均 {home_lambda:.2f} 球）。"
        )
    elif away_lambda > home_lambda + 0.4:
        reasons.append(
            f"模型预计 {away.name_zh} 进攻效率更高（场均 {away_lambda:.2f} 球）。"
        )

    # 3) B2: 近期状态因子
    if home_form is not None and away_form is not None:
        if home_form - away_form >= 4:
            reasons.append(
                f"{home.name_zh} 近 5 场拿 {home_form} 分，状态明显好于 {away.name_zh}（{away_form} 分）。"
            )
        elif away_form - home_form >= 4:
            reasons.append(
                f"{away.name_zh} 近 5 场拿 {away_form} 分，状态明显好于 {home.name_zh}（{home_form} 分）。"
            )
        else:
            reasons.append(
                f"两队近 5 场状态接近（{home_form} vs {away_form} 分），均无明显状态优势。"
            )

    # 4) B3: H2H
    if h2h["sample"] > 0:
        reasons.append(f"历史交锋：{h2h['summary']}。")

    # 5) 结论 / 兜底
    if home_win > 0.5:
        reasons.append("综合胜率超过 50%，主队略被看好。")
    elif home_win < 0.25:
        reasons.append("客队取胜概率较高，主队需放低姿态主打反击。")
    else:
        reasons.append("主客场差距有限，结果不确定性较高。")

    # 至少 3 条
    if len(reasons) < 3:
        reasons.append("世界杯为中立场地，主场优势相对有限。")
    if len(reasons) < 3:
        reasons.append("临场状态、伤停、天气等随机因素可能显著影响结果。")

    return reasons[:5]


def predict_match(
    home: Team,
    away: Team,
    match: Match,
    db: Optional[Session] = None,
) -> PredictionOut:
    """为一场比赛生成 Elo-Poisson v1 预测.

    整合 B1（Elo 校准）/ B2（近期状态 λ 调整）/ B3（H2H 查表）。
    """
    # B1: 用 fifa_rank 校准后的 Elo（已是 home.elo_rating，seed 时已校准）
    home_lambda, away_lambda = _elo_to_lambda(home.elo_rating, away.elo_rating)
    home_lambda, away_lambda = _apply_recent_form(
        home_lambda, away_lambda, home.recent_form_points, away.recent_form_points
    )

    home_win, draw, away_win, best_score = _predict_score_distribution(home_lambda, away_lambda)
    stars = _stars(home_win, draw, away_win)

    h2h = _query_h2h(db, home, away)
    reasons = _reasons(
        home, away, home_lambda, away_lambda, home_win,
        home.recent_form_points, away.recent_form_points, h2h
    )

    # F2: 计算可解释性因子贡献
    factors = _factors_breakdown(
        home, away, home_lambda, away_lambda,
        home.recent_form_points, away.recent_form_points, h2h
    )

    # H2H 在 schema 里只接受"无方向"的胜平负统计，我们归一到"home 视角"
    h2h_record = None
    if h2h["sample"] > 0:
        h2h_record = {
            "home_wins": h2h["home_wins"],
            "away_wins": h2h["away_wins"],
            "draws": h2h["draws"],
            "sample": h2h["sample"],
        }

    return PredictionOut(
        match_id=match.id,
        home_win_prob=round(home_win * 100, 1),
        draw_prob=round(draw * 100, 1),
        away_win_prob=round(away_win * 100, 1),
        expected_home_goals=round(home_lambda, 2),
        expected_away_goals=round(away_lambda, 2),
        recommended_score=best_score,
        stars=stars,
        reasons=reasons,
        h2h_summary=h2h["summary"] or None,
        h2h_record=h2h_record,
        home_recent_form=_form_string(home.recent_form_points),
        away_recent_form=_form_string(away.recent_form_points),
        factors_breakdown=factors,
    )
