"""淘汰赛 Bracket API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.bracket_logic import build_bracket


router = APIRouter()


@router.get("/bracket")
def get_bracket(db: Session = Depends(get_db)) -> dict:
    """获取 2026 世界杯淘汰赛对阵树（含 Elo 预测）.

    小组赛未结束时返回基于当前积分榜的推演结果，并标记 group_stage_finished=false。
    """
    return build_bracket(db)
