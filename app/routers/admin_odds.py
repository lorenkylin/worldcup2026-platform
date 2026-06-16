"""管理后台 API - 赔率手动录入（M3）.

Endpoint:
  POST /api/admin/odds          单条录入
  POST /api/admin/odds/batch    批量录入
  DELETE /api/admin/odds/{id}   删除单条

所有端点需要 X-Admin-Token 头,与 admin.py 一致.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Match, MatchOdds
from app.schemas import OddsCreateIn, OddsBatchCreateIn, OddsOut


router = APIRouter()


def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    """校验管理员 Token."""
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="管理员 Token 无效")


def _validate_odds(payload: OddsCreateIn) -> None:
    """校验赔率范围 + 比赛存在性."""
    if payload.match_id <= 0:
        raise HTTPException(status_code=400, detail="match_id 无效")
    for field in ("home_win", "draw", "away_win", "over_2_5", "under_2_5"):
        val = getattr(payload, field)
        if val is not None and (val < 1.01 or val > 1000.0):
            raise HTTPException(
                status_code=400,
                detail=f"{field} 赔率 {val} 超出范围 [1.01, 1000.0]",
            )


@router.post("/odds", response_model=OddsOut)
def create_odds(
    payload: OddsCreateIn,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> MatchOdds:
    """手动录入单条赔率（同 match_id + bookmaker 覆盖式更新）."""
    _validate_odds(payload)

    # 检查比赛存在
    match = db.query(Match).filter(Match.id == payload.match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail=f"比赛 {payload.match_id} 不存在")

    # 覆盖式：同 (match_id, bookmaker) 取最近一条更新
    existing = (
        db.query(MatchOdds)
        .filter(MatchOdds.match_id == payload.match_id, MatchOdds.bookmaker == payload.bookmaker)
        .order_by(MatchOdds.fetched_at.desc())
        .first()
    )

    if existing:
        existing.home_win = payload.home_win
        existing.draw = payload.draw
        existing.away_win = payload.away_win
        existing.over_2_5 = payload.over_2_5
        existing.under_2_5 = payload.under_2_5
        existing.source = payload.source
        existing.fetched_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    odds = MatchOdds(
        match_id=payload.match_id,
        bookmaker=payload.bookmaker,
        home_win=payload.home_win,
        draw=payload.draw,
        away_win=payload.away_win,
        over_2_5=payload.over_2_5,
        under_2_5=payload.under_2_5,
        source=payload.source,
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(odds)
    db.commit()
    db.refresh(odds)
    return odds


@router.post("/odds/batch")
def create_odds_batch(
    payload: OddsBatchCreateIn,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> dict:
    """批量录入赔率（每条独立校验,失败条目计数返回）."""
    inserted = 0
    updated = 0
    failed = []

    for idx, item in enumerate(payload.items):
        try:
            _validate_odds(item)
            match = db.query(Match).filter(Match.id == item.match_id).first()
            if not match:
                failed.append({"index": idx, "match_id": item.match_id, "error": "比赛不存在"})
                continue

            existing = (
                db.query(MatchOdds)
                .filter(MatchOdds.match_id == item.match_id, MatchOdds.bookmaker == item.bookmaker)
                .order_by(MatchOdds.fetched_at.desc())
                .first()
            )
            if existing:
                existing.home_win = item.home_win
                existing.draw = item.draw
                existing.away_win = item.away_win
                existing.over_2_5 = item.over_2_5
                existing.under_2_5 = item.under_2_5
                existing.source = item.source
                existing.fetched_at = datetime.now(timezone.utc)
                updated += 1
            else:
                db.add(MatchOdds(
                    match_id=item.match_id,
                    bookmaker=item.bookmaker,
                    home_win=item.home_win,
                    draw=item.draw,
                    away_win=item.away_win,
                    over_2_5=item.over_2_5,
                    under_2_5=item.under_2_5,
                    source=item.source,
                    fetched_at=datetime.now(timezone.utc),
                ))
                inserted += 1
        except HTTPException as exc:
            failed.append({"index": idx, "match_id": item.match_id, "error": exc.detail})
            db.rollback()  # 单条失败回滚（SQLite 单事务）
        except Exception as exc:  # noqa: BLE001
            failed.append({"index": idx, "match_id": item.match_id, "error": str(exc)})
            db.rollback()

    db.commit()
    return {
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "failed": failed,
        "total": len(payload.items),
    }


@router.delete("/odds/{odds_id}")
def delete_odds(
    odds_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
) -> dict:
    """删除单条赔率."""
    odds = db.query(MatchOdds).filter(MatchOdds.id == odds_id).first()
    if not odds:
        raise HTTPException(status_code=404, detail="赔率记录不存在")
    db.delete(odds)
    db.commit()
    return {"ok": True, "message": f"赔率 {odds_id} 已删除"}
