"""预测相关 API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Match
from app.schemas import PredictionOut
from app.services.prediction import predict_match
from app.services.prediction_cache import (
    get_cached_prediction,
    set_cached_prediction,
    get_cache_stats,
)


router = APIRouter()


@router.get("/matches/{match_id}/prediction", response_model=PredictionOut)
def get_prediction(match_id: int, db: Session = Depends(get_db)) -> PredictionOut:
    """获取某场比赛的 Elo-Poisson v1 预测（含 B2 近期状态 / B3 H2H / F1 5 分钟缓存）."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if not match.home_team or not match.away_team:
        raise HTTPException(status_code=400, detail="该对阵尚不确定，无法预测")

    # F1: 尝试命中缓存（DB 读 + JSON 反序列化，< 5ms）
    cached = get_cached_prediction(db, match, match.home_team, match.away_team)
    if cached is not None:
        return cached

    # 缓存未命中 → 跑完整计算
    prediction = predict_match(match.home_team, match.away_team, match, db=db)

    # 写缓存
    set_cached_prediction(db, match, match.home_team, match.away_team, prediction)

    return prediction


@router.get("/predictions/cache/stats")
def cache_stats(db: Session = Depends(get_db)) -> dict:
    """F1 缓存统计（公开，仅返回元数据）."""
    return get_cache_stats(db)

