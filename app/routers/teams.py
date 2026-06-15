"""球队相关 API."""

from typing import List, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db import get_db
from app.models import Team, Match
from app.schemas import TeamOut, MatchOut


router = APIRouter()


@router.get("/teams", response_model=List[TeamOut])
def list_teams(db: Session = Depends(get_db)) -> List[Team]:
    """获取全部球队列表."""
    return db.query(Team).order_by(Team.group_name, Team.name_zh).all()


def _resolve_team(db: Session, code: str) -> Team:
    """用 team_id（int 字符串）或 fifa_code（如 'BRA'）解析球队.

    兼容两种客户端：内部调用方用 int ID，外部 API 用户用 FIFA 3 字母代码。
    """
    if code.isdigit():
        team = db.query(Team).filter(Team.id == int(code)).first()
    else:
        team = db.query(Team).filter(Team.fifa_code == code.upper()).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"球队不存在: {code}")
    return team


@router.get("/teams/{team_code}", response_model=TeamOut)
def get_team(team_code: str, db: Session = Depends(get_db)) -> Team:
    """获取球队详情（支持 team_id 数字或 FIFA 代码如 'BRA'）."""
    return _resolve_team(db, team_code)


@router.get("/teams/{team_code}/matches", response_model=List[MatchOut])
def team_matches(team_code: str, db: Session = Depends(get_db)) -> List[Match]:
    """获取某支球队的全部比赛（支持 team_id 数字或 FIFA 代码）."""
    team = _resolve_team(db, team_code)
    return (
        db.query(Match)
        .filter((Match.home_team_id == team.id) | (Match.away_team_id == team.id))
        .order_by(Match.kickoff_at)
        .all()
    )
