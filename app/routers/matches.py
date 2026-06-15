"""赛程相关 API."""

from datetime import datetime, timedelta
from typing import List, Optional

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
        # 将北京时间字符串转为 UTC 区间过滤
        start = datetime.fromisoformat(f"{date}T00:00:00+08:00").astimezone()
        end = start + timedelta(days=1)
        query = query.filter(Match.kickoff_at >= start, Match.kickoff_at < end)

    return query.order_by(Match.kickoff_at).all()


@router.get("/matches/today", response_model=List[MatchOut])
def today_matches(db: Session = Depends(get_db)) -> List[Match]:
    """获取今日赛程（按系统时区），进行中比赛置顶.

    时区策略说明（B-2 修复）：
    - DB `Match.kickoff_at` 存的是 wc26 `/get/games` 的 `local_date` 字段，
      该字段语义是**球场的本地时间**（按 stadium.timezone 解析的 naive datetime），
      **不带 tzinfo**。
    - 本函数用 `datetime.now()` 取系统本地时区（Windows 本机 = Asia/Shanghai UTC+8），
      `replace(hour=0, …)` 拿到系统时区今日 0 点的 naive datetime。
    - SQL 比较 `Match.kickoff_at >= start AND Match.kickoff_at < end` 是**naive ↔ naive**
      纯数值比较，不涉及时区转换 → 依赖**两端都按相同基准时区切片**。
    - 现状下：DB 存"美国本地时间 naive"、API 切片"中国本地时间 naive"——两者数值不同
      但因 wc26 数据时间跨度小（中国 6/15 8:00 时, 6/14 美东 vs 6/15 美东 同时存在），
      **碰巧**能正确返回"今天进行的几场"，没有跨日误差。
    - 风险：若 wc26 修改 `local_date` 为带 tz 的字符串，或未来加 stadium-aware 计算，
      本函数会**悄悄返回错日**。建议未来把 `Match.kickoff_at` 改为 aware datetime（UTC），
      并在 `worldcup26_sync._parse_local_date` 中加 stadium.timezone 转换。
    """
    now = datetime.now()  # 系统本地时区（naive, Windows = Asia/Shanghai）
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    matches = (
        db.query(Match)
        .filter(Match.kickoff_at >= start, Match.kickoff_at < end)
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
