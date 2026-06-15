"""出线模拟器 API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.simulator import simulate_group_advancement


router = APIRouter()


@router.get("/simulator/groups")
def group_advancement(db: Session = Depends(get_db)) -> dict:
    """运行 5000 次蒙特卡洛模拟，返回每队出线概率.

    返回格式：{ "groups": [{"group_name": "A", "teams": [...]}], "simulations": 5000 }
    """
    odds = simulate_group_advancement(db)
    groups: dict[str, list] = {}
    for o in odds:
        groups.setdefault(o.group_name, []).append({
            "team_id": o.team_id,
            "team_name": o.team_name,
            "flag_emoji": o.flag_emoji,
            "points": o.points,
            "goal_diff": o.goal_diff,
            "goals_for": o.goals_for,
            "direct_qualify_prob": o.direct_qualify_prob,
            "third_place_prob": o.third_place_prob,
            "eliminated_prob": o.eliminated_prob,
            "advance_overall_prob": o.advance_overall_prob,
        })
    return {
        "simulations": 5000,
        "groups": [
            {"group_name": gn, "teams": ts}
            for gn, ts in sorted(groups.items())
        ],
    }