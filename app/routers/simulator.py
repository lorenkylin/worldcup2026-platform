"""出线模拟器 API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.simulator import simulate_group_advancement
from app.services.monte_carlo import (
    MAX_SIMULATIONS,
    MIN_SIMULATIONS,
    DEFAULT_SIMULATIONS,
    run_mc_with_cache,
)


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


@router.get("/simulator/tournament")
def tournament(
    simulations: int = Query(
        DEFAULT_SIMULATIONS, ge=MIN_SIMULATIONS, le=MAX_SIMULATIONS,
        description=f"模拟次数, 范围 [{MIN_SIMULATIONS}, {MAX_SIMULATIONS}]",
    ),
    model: str = Query("blend", description="blend | elo | glicko2"),
    return_top_n: int = Query(8, ge=1, le=20, description="top N 对阵频率"),
    seed: int = Query(42, description="随机种子 (用于可重现)"),
    refresh: bool = Query(False, description="1=强制跳过缓存, 重新计算"),
    db: Session = Depends(get_db),
) -> dict:
    """v0.7.1.1 整届 2026 世界杯蒙特卡洛(带 6h 缓存).

    跑 N 次完整小组赛 + R32 + R16 + QF + SF + 3rd + Final, 统计每队各轮次晋级概率。
    默认优先读取 6h 内缓存;?refresh=1 强制重算。

    Args:
        simulations: 模拟次数, 默认 10000
        model: 预测模型 blend | elo | glicko2
        return_top_n: top N 决赛/半决赛对阵频率
        seed: 随机种子, 默认 42 (可重现)
        refresh: 是否强制跳过缓存

    Returns:
        见 deliverables/v0.7.1_spec.md
    """
    if model not in ("blend", "elo", "glicko2"):
        raise HTTPException(
            status_code=422,
            detail=f"model 必须是 'blend' / 'elo' / 'glicko2', 收到 {model!r}",
        )

    try:
        return run_mc_with_cache(
            db,
            n_sims=simulations,
            model=model,
            return_top_n=return_top_n,
            seed=seed,
            refresh=refresh,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
