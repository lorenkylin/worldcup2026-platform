"""管理后台 API（手动比分/事件/统计更新）."""

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Match, MatchEvent, MatchStats, Standing, Team
from app.schemas import ScoreUpdateIn, EventCreateIn, StatsCreateIn
from app.services.bracket_logic import rebuild_bracket


router = APIRouter()


def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    """校验管理员 Token（常量时间比较，防止定时攻击）.

    当未配置 admin_token 时默认关闭管理端点，避免空 token 被绕过。
    """
    if not settings.admin_token or not hmac.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=403, detail="管理员 Token 无效")


@router.post("/matches/{match_id}/score")
def update_score(
    match_id: int,
    payload: ScoreUpdateIn,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动更新比赛比分与状态."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    match.home_score = payload.home_score
    match.away_score = payload.away_score
    match.status = payload.status
    match.time_elapsed = payload.time_elapsed
    match.last_updated_at = datetime.now(timezone.utc)
    match.data_source = "manual"

    db.commit()

    # 若比赛结束，同步积分榜
    if payload.status == "finished" and match.group_name:
        _update_standing(db, match)

    return {"ok": True, "message": "比分已更新"}


@router.post("/matches/{match_id}/events")
def add_event(
    match_id: int,
    payload: EventCreateIn,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动录入比赛事件."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    event = MatchEvent(
        match_id=match_id,
        team_id=payload.team_id,
        event_type=payload.event_type,
        minute=payload.minute,
        player_name=payload.player_name,
        extra_info=payload.extra_info,
    )
    db.add(event)
    db.commit()
    return {"ok": True, "message": "事件已录入"}


@router.post("/matches/{match_id}/stats")
def add_stats(
    match_id: int,
    payload: StatsCreateIn,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动录入赛后统计."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    # 先删除旧统计（同队）
    db.query(MatchStats).filter(
        MatchStats.match_id == match_id, MatchStats.team_id == payload.team_id
    ).delete()

    stats = MatchStats(match_id=match_id, **payload.model_dump())
    db.add(stats)
    db.commit()
    return {"ok": True, "message": "统计已录入"}


def _update_standing(db: Session, match: Match) -> None:
    """根据比赛结果更新小组赛积分榜."""
    home = match.home_team
    away = match.away_team
    if not home or not away or not match.group_name:
        return

    for team, goals_for, goals_against in (
        (home, match.home_score or 0, match.away_score or 0),
        (away, match.away_score or 0, match.home_score or 0),
    ):
        standing = (
            db.query(Standing)
            .filter_by(group_name=match.group_name, team_id=team.id)
            .first()
        )
        if not standing:
            standing = Standing(group_name=match.group_name, team_id=team.id)
            db.add(standing)

        standing.played = (standing.played or 0) + 1
        standing.goals_for = (standing.goals_for or 0) + goals_for
        standing.goals_against = (standing.goals_against or 0) + goals_against
        if goals_for > goals_against:
            standing.won = (standing.won or 0) + 1
            standing.points = (standing.points or 0) + 3
        elif goals_for == goals_against:
            standing.drawn = (standing.drawn or 0) + 1
            standing.points = (standing.points or 0) + 1
        else:
            standing.lost = (standing.lost or 0) + 1
        standing.updated_at = datetime.now(timezone.utc)

    db.commit()


@router.post("/bracket/rebuild")
def rebuild_bracket_endpoint(
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动触发 Bracket 重新计算并持久化到 matches 表."""
    return rebuild_bracket(db)
