"""小组积分榜相关 API."""

from collections import defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Team, Standing
from app.schemas import GroupStandingOut, TeamOut


router = APIRouter()


@router.get("/groups", response_model=Dict[str, List[GroupStandingOut]])
def group_standings(db: Session = Depends(get_db)) -> Dict[str, List[dict]]:
    """获取全部 12 个小组的积分榜."""
    teams = db.query(Team).all()
    standings = db.query(Standing).all()
    standing_map = {s.team_id: s for s in standings}

    result: Dict[str, List[dict]] = defaultdict(list)
    for team in teams:
        s = standing_map.get(team.id)
        result[team.group_name].append(
            {
                "team": TeamOut.model_validate(team),
                "played": s.played if s else 0,
                "won": s.won if s else 0,
                "drawn": s.drawn if s else 0,
                "lost": s.lost if s else 0,
                "goals_for": s.goals_for if s else 0,
                "goals_against": s.goals_against if s else 0,
                "points": s.points if s else 0,
            }
        )

    # 排序：积分 > 净胜球 > 进球
    for group_name in result:
        result[group_name].sort(
            key=lambda x: (x["points"], x["goals_for"] - x["goals_against"], x["goals_for"]),
            reverse=True,
        )

    return dict(result)
