"""赛程相关 API."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Match
from app.schemas import MatchOut
from app.services.weather import get_weather_for_match, weather_label


router = APIRouter()


@router.get("/matches", response_model=List[MatchOut])
def list_matches(
    db: Session = Depends(get_db),
    date: str = Query(None, description="比赛日，格式 YYYY-MM-DD（北京时间）"),
    group: str = Query(None, description="小组名，例如 A"),
    status: str = Query(None, description="比赛状态 scheduled/live/finished"),
) -> List[Match]:
    """获取赛程列表，支持按日期、小组、状态过滤."""
    query = db.query(Match)
    if group:
        query = query.filter(Match.group_name == group.upper())
    if status:
        query = query.filter(Match.status == status)
    if date:
        # DB 存 UTC，但接口 date 语义是北京时间比赛日；先构造北京时间 0 点，再转 UTC
        beijing_start = datetime.fromisoformat(f"{date}T00:00:00+08:00")
        utc_start = beijing_start.astimezone(timezone.utc).replace(tzinfo=None)
        utc_end = utc_start + timedelta(days=1)
        query = query.filter(Match.kickoff_at >= utc_start, Match.kickoff_at < utc_end)

    return query.order_by(Match.kickoff_at).all()


@router.get("/matches/today", response_model=List[MatchOut])
def today_matches(db: Session = Depends(get_db)) -> List[Match]:
    """获取今日赛程（按北京时间），进行中比赛置顶.

    DB `Match.kickoff_at` 已统一存 UTC；本函数以 UTC 计算北京时间的今日 0 点区间。
    """
    now_utc = datetime.now(timezone.utc)
    # 当前 UTC 时间对应的北京时间日期
    beijing_now = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    beijing_start = beijing_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = beijing_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = utc_start + timedelta(days=1)
    matches = (
        db.query(Match)
        .filter(Match.kickoff_at >= utc_start, Match.kickoff_at < utc_end)
        .order_by(Match.kickoff_at)
        .all()
    )
    # 进行中置顶
    return sorted(matches, key=lambda m: (m.status != "live", m.kickoff_at))


@router.get("/matches/{match_id}", response_model=MatchOut)
def get_match(match_id: int, db: Session = Depends(get_db)) -> Match:
    """获取单场比赛详情（含事件与统计）."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")
    # 显式触发 lazy load
    _ = match.events, match.stats
    return match


@router.get("/matches/{match_id}/weather")
def match_weather(match_id: int, db: Session = Depends(get_db)) -> dict:
    """查询比赛当日球场天气（Open-Meteo 免费）.

    返回：{date, lat, lng, temperature, precipitation, windspeed, weathercode, label, source}
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match or not match.stadium:
        raise HTTPException(status_code=404, detail="比赛或球场不存在")
    stadium = match.stadium
    if stadium.latitude is None or stadium.longitude is None:
        return {"date": match.kickoff_at.date().isoformat(), "available": False,
                "message": "该球场经纬度尚未录入", "stadium": stadium.name_en}
    date_str = match.kickoff_at.date().isoformat()
    weather = get_weather_for_match(stadium.latitude, stadium.longitude, date_str)
    if not weather:
        return {"date": date_str, "available": False,
                "message": "天气服务暂时不可用", "stadium": stadium.name_en}
    return {
        "available": True,
        "date": date_str,
        "stadium": stadium.name_en,
        "city": stadium.city,
        "lat": stadium.latitude,
        "lng": stadium.longitude,
        "temperature": weather.get("temperature"),
        "precipitation": weather.get("precipitation", 0),
        "windspeed": weather.get("windspeed"),
        "weathercode": weather.get("weathercode"),
        "label": weather_label(weather.get("weathercode")),
        "source": "open-meteo",
    }
