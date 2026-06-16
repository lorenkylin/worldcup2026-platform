"""赔率查询 API（M3 + v0.5.1 走势）.

Endpoint:
  GET /api/matches/{id}/odds          单场赔率 + 市场隐含概率（去 vig）
  GET /api/matches/{id}/odds/history  单场赔率走势(v0.5.1,多公司多时间点)
  GET /api/odds/compare               所有未完赛比赛赔率 vs Elo 对比
  GET /api/odds/value-bets            价值投注 TOP N（best_value != None）

所有端点公开,无需鉴权.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Match, MatchOdds, OddsSnapshot, Team
from app.services.odds_service import (
    aggregate_multi_bookmaker,
    compare_odds_vs_elo,
    compute_market_probabilities,
)
from app.services.elo import predict_match
from app.schemas import OddsOut


router = APIRouter()


def _latest_odds_per_bookmaker(db: Session, match_id: int) -> List[MatchOdds]:
    """取某场比赛每个 bookmaker 最新一条赔率."""
    rows = (
        db.query(MatchOdds)
        .filter(MatchOdds.match_id == match_id)
        .order_by(MatchOdds.fetched_at.desc())
        .all()
    )
    seen = set()
    latest = []
    for r in rows:
        if r.bookmaker not in seen:
            seen.add(r.bookmaker)
            latest.append(r)
    return latest


def _build_compare_items(db: Session, stage: Optional[str], limit: int) -> list:
    """构建赔率 vs Elo 对比的核心逻辑(供 /compare 和 /value-bets 共用).

    Returns:
        list[dict]: 比赛对比结果列表
    """
    q = db.query(Match).filter(Match.status != "finished")
    if stage:
        q = q.filter(Match.stage == stage)
    matches = q.order_by(Match.kickoff_at).limit(limit * 3).all()

    results = []
    for m in matches:
        odds_rows = _latest_odds_per_bookmaker(db, m.id)
        if not odds_rows:
            continue

        # 取 consensus(平均)
        odds_dicts = [
            {"home_win": r.home_win, "draw": r.draw, "away_win": r.away_win}
            for r in odds_rows
            if r.home_win and r.draw and r.away_win
        ]
        if not odds_dicts:
            continue
        avg = aggregate_multi_bookmaker(odds_dicts)
        if not (avg["home_win"] and avg["draw"] and avg["away_win"]):
            continue

        # 算 Elo 概率
        home_code = m.home_team.fifa_code if m.home_team else None
        away_code = m.away_team.fifa_code if m.away_team else None
        if not home_code or not away_code:
            continue
        elo_result = predict_match(home_code, away_code, source="hicruben")
        if elo_result.get("error"):
            continue

        elo_probs = {
            "home_prob": elo_result["probabilities"]["home_win"],
            "draw_prob": elo_result["probabilities"]["draw"],
            "away_prob": elo_result["probabilities"]["away_win"],
        }
        cmp = compare_odds_vs_elo(
            avg["home_win"], avg["draw"], avg["away_win"],
            elo_probs["home_prob"], elo_probs["draw_prob"], elo_probs["away_prob"],
        )

        results.append({
            "match_id": m.id,
            "match_number": m.match_number,
            "stage": m.stage,
            "group_name": m.group_name,
            "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
            "home_team": {
                "fifa_code": home_code,
                "name_zh": m.home_team.name_zh if m.home_team else "",
                "elo": elo_result.get("home", {}).get("elo"),
            },
            "away_team": {
                "fifa_code": away_code,
                "name_zh": m.away_team.name_zh if m.away_team else "",
                "elo": elo_result.get("away", {}).get("elo"),
            },
            "market": cmp["market"],
            "elo": cmp["elo"],
            "value_bet": cmp["value_bet"],
            "best_value": cmp["best_value"],
            "best_value_rate": cmp["best_value_rate"],
        })
        if len(results) >= limit:
            break

    return results


@router.get("/matches/{match_id}/odds")
def get_match_odds(
    match_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """获取某场比赛的最新赔率 + 市场隐含概率(去 vig).

    Returns:
        {
          match_id, has_odds,
          bookmakers: [{bookmaker, odds:{home_win,draw,away_win,over_2_5,under_2_5},
                        market_prob:{home_prob,draw_prob,away_prob,total_vig},
                        fetched_at, source}],
          consensus: {odds, market_prob},  # 多家平均
        }
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    odds_rows = _latest_odds_per_bookmaker(db, match_id)
    if not odds_rows:
        return {
            "match_id": match_id,
            "has_odds": False,
            "message": "该比赛暂无赔率, 请联系管理员录入",
            "bookmakers": [],
            "consensus": None,
        }

    bookmakers = []
    odds_dicts = []
    for r in odds_rows:
        odds_dict = {
            "home_win": r.home_win,
            "draw": r.draw,
            "away_win": r.away_win,
            "over_2_5": r.over_2_5,
            "under_2_5": r.under_2_5,
        }
        odds_dicts.append(odds_dict)

        market_prob = None
        if r.home_win and r.draw and r.away_win:
            market_prob = compute_market_probabilities(r.home_win, r.draw, r.away_win)

        bookmakers.append({
            "bookmaker": r.bookmaker,
            "odds": odds_dict,
            "market_prob": market_prob,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            "source": r.source,
        })

    full_odds = [o for o in odds_dicts if all(o[k] for k in ("home_win", "draw", "away_win"))]
    consensus = None
    if full_odds:
        avg = aggregate_multi_bookmaker(full_odds)
        if avg["home_win"] and avg["draw"] and avg["away_win"]:
            consensus = {
                "odds": avg,
                "market_prob": compute_market_probabilities(avg["home_win"], avg["draw"], avg["away_win"]),
            }

    return {
        "match_id": match_id,
        "has_odds": True,
        "bookmakers": bookmakers,
        "consensus": consensus,
    }


@router.get("/odds/compare")
def compare_odds_vs_elo_all(
    db: Session = Depends(get_db),
    stage: Optional[str] = Query(None, description="过滤 stage: 小组赛/16强/..."),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """所有未完赛比赛: 赔率(consensus) vs Elo 概率 + value bet."""
    items = _build_compare_items(db, stage=stage, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/odds/value-bets")
def value_bets(
    db: Session = Depends(get_db),
    min_rate: float = Query(0.05, ge=0, le=1.0, description="最小 value bet 率, 默认 5%"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """价值投注 TOP N: best_value_rate >= min_rate 的比赛,按 rate 降序."""
    items = _build_compare_items(db, stage=None, limit=200)
    items = [it for it in items if it["best_value_rate"] >= min_rate]
    items.sort(key=lambda x: x["best_value_rate"], reverse=True)
    return {"count": min(len(items), limit), "min_rate": min_rate, "items": items[:limit]}


@router.get("/matches/{match_id}/odds/history")
def get_match_odds_history(
    match_id: int,
    db: Session = Depends(get_db),
    bookmaker: Optional[str] = Query(None, description="过滤 bookmaker, 不传则返回全部"),
) -> dict:
    """v0.5.1 单场赔率走势（用于 Chart.js 折线图）.

    返回每个 bookmaker 的时间序列,适合直接喂给 Chart.js datasets.

    Returns:
        {
          match_id, has_history,
          bookmakers: [bookmaker 名称列表],
          series: {
            "<bookmaker>": [
              {t: ISO8601, home_win, draw, away_win, over_2_5, under_2_5, source},
              ...
            ]
          },
          count: snapshot 总数
        }
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    q = db.query(OddsSnapshot).filter(OddsSnapshot.match_id == match_id)
    if bookmaker:
        q = q.filter(OddsSnapshot.bookmaker == bookmaker)
    snapshots = q.order_by(OddsSnapshot.snapshot_at.asc()).all()

    if not snapshots:
        return {
            "match_id": match_id,
            "has_history": False,
            "message": "该比赛暂无赔率快照(可能尚未录入赔率或 6h 调度器尚未运行)",
            "bookmakers": [],
            "series": {},
            "count": 0,
        }

    # 按 bookmaker 分组,每个 series 按时间升序
    series: dict = {}
    for s in snapshots:
        bm = s.bookmaker
        if bm not in series:
            series[bm] = []
        series[bm].append({
            "t": s.snapshot_at.isoformat() if s.snapshot_at else None,
            "home_win": s.home_win,
            "draw": s.draw,
            "away_win": s.away_win,
            "over_2_5": s.over_2_5,
            "under_2_5": s.under_2_5,
            "source": s.source,
        })

    return {
        "match_id": match_id,
        "has_history": True,
        "bookmakers": list(series.keys()),
        "series": series,
        "count": len(snapshots),
    }


@router.get("/odds/latest")
def odds_latest(db: Session = Depends(get_db)) -> dict:
    """v0.6.0: 全局最新赔率快照时间(用于前端"数据更新于 X 分钟前"展示).

    Returns:
        {
          "latest_fetched_at": ISO-8601 或 null,
          "snapshot_count": int,
          "minutes_ago": float 或 null (距今分钟数)
        }
    """
    from sqlalchemy import func

    n = db.query(func.count(OddsSnapshot.id)).scalar() or 0
    latest = db.query(OddsSnapshot).order_by(OddsSnapshot.snapshot_at.desc()).first()
    if not latest or not latest.snapshot_at:
        return {"latest_fetched_at": None, "snapshot_count": n, "minutes_ago": None}

    # 统一为 UTC aware 比较
    ts = latest.snapshot_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    return {
        "latest_fetched_at": ts.isoformat(),
        "snapshot_count": n,
        "minutes_ago": round(delta, 1),
    }
