"""Cockpit 总览驾驶舱 API（v0.14.2）.

单一聚合端点，为新版总览页提供统计 + 总预览 + 互联互通数据。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.cockpit import build_cockpit_summary

router = APIRouter(prefix="/cockpit", tags=["总览驾驶舱"])


@router.get("/summary")
def cockpit_summary(db: Session = Depends(get_db)) -> dict:
    """总览驾驶舱聚合摘要.

    返回：
    - tournament_progress: 赛事进度与淘汰赛里程碑
    - qualification_summary: 晋级/淘汰/最佳第 3 名概览
    - data_health: 数据源健康 + 同步状态
    - critical_matches: 未来 72h 关键战（含模型共识、出线影响标签）
    - model_consensus: 模型高共识高置信比赛
    - market_model_divergence: 市场 vs 模型偏离价值投注
    - elo_top_teams: Elo Top 5
    """
    return build_cockpit_summary(db)
