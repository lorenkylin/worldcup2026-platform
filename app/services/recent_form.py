"""B2 配套：从已完成比赛回填每队的 recent_form_points / recent_goal_diff.

策略：用"本届赛事已完赛场次"作为该队的近期状态因子。
- 优点：单一数据源（worldcup26.ir 已含结果），不引入第二数据源
- 反馈：比赛完 → 自动回填 → 下场比赛预测就能用到
- 失败安全：未完赛球队保持 None，预测模型会优雅降级跳过 B2
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models import Match, Team


# 每场胜 3 平 1 负 0
POINTS_WIN = 3
POINTS_DRAW = 1
POINTS_LOSS = 0


def _result_for_team(match: Match, team_id: int) -> Tuple[int, int, int]:
    """从 home 视角归一返回 (points, goals_for, goals_against)."""
    if match.home_score is None or match.away_score is None:
        return 0, 0, 0

    if match.home_team_id == team_id:
        gf, ga = match.home_score, match.away_score
    elif match.away_team_id == team_id:
        gf, ga = match.away_score, match.home_score
    else:
        return 0, 0, 0

    if gf > ga:
        return POINTS_WIN, gf, ga
    if gf == ga:
        return POINTS_DRAW, gf, ga
    return POINTS_LOSS, gf, ga


def _team_recent(db: Session, team_id: int, lookback: int) -> Tuple[int, int, int]:
    """返回 (累计积分, 累计进失球差, 样本数)."""
    matches: List[Match] = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
            ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)),
        )
        .order_by(Match.kickoff_at.desc())
        .limit(lookback)
        .all()
    )
    total_pts = 0
    total_gd = 0
    for m in matches:
        pts, gf, ga = _result_for_team(m, team_id)
        total_pts += pts
        total_gd += gf - ga
    return total_pts, total_gd, len(matches)


def compute_and_persist_recent_form(db: Session, lookback: int = 5) -> Dict:
    """扫描全表，按 (team, 最近 lookback 场) 回填 recent_form_points / recent_goal_diff.

    Returns:
        {
            "teams_updated": int,
            "teams_with_data": int,
            "matches_scanned": int,
            "synced_at": iso8601,
        }
    """
    teams = db.query(Team).all()

    # 先扫一遍统计比赛数（用于报告）
    matches_scanned = (
        db.query(Match)
        .filter(Match.status == "finished", Match.home_score.isnot(None))
        .count()
    )

    teams_updated = 0
    teams_with_data = 0
    for team in teams:
        if team.id is None:
            continue
        pts, gd, sample = _team_recent(db, team.id, lookback)
        if sample == 0:
            # 保持 None — 预测模型会跳过该因子
            if team.recent_form_points is not None:
                team.recent_form_points = None
                team.recent_goal_diff = None
                db.add(team)
                teams_updated += 1
            continue

        if team.recent_form_points != pts or team.recent_goal_diff != gd:
            team.recent_form_points = pts
            team.recent_goal_diff = gd
            db.add(team)
            teams_updated += 1
        teams_with_data += 1

    db.commit()
    return {
        "teams_updated": teams_updated,
        "teams_with_data": teams_with_data,
        "matches_scanned": matches_scanned,
        "lookback": lookback,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def backfill_after_sync(db: Session) -> Dict:
    """worldcup26_full_sync 完成后调用 — 一次回填。"""
    return compute_and_persist_recent_form(db, lookback=5)
