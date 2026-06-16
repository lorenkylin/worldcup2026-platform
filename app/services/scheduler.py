"""APScheduler 调度任务定义.

零预算路线：仅调度免费源 + 手动兜底，不调度任何付费 API。
"""

from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.config import settings


def _job_worldcup26_pull(session_factory: Callable, sync_fn: Callable) -> None:
    """定时拉取 worldcup26.ir 全部数据."""
    db: Session = session_factory()
    try:
        result = sync_fn(db)
        print(f"[{datetime.now().isoformat()}] worldcup26.ir 同步: {result}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now().isoformat()}] worldcup26.ir 同步失败: {exc}")
    finally:
        db.close()


def build_default_jobs(
    scheduler: BackgroundScheduler,
    session_factory: Callable,
    sync_fn: Callable,
) -> None:
    """注册默认轮询任务.

    Args:
        scheduler: APScheduler 实例。
        session_factory: SQLAlchemy SessionLocal。
        sync_fn: 同步函数（应可接收 db Session 并返回 dict）。
    """
    interval = max(settings.sync_interval_seconds, 60)  # 至少 60 秒

    # 主源：worldcup26.ir 全量同步
    scheduler.add_job(
        _job_worldcup26_pull,
        trigger=IntervalTrigger(seconds=interval),
        args=[session_factory, sync_fn],
        id="worldcup26_full_sync",
        name=f"worldcup26.ir 全量同步（每 {interval}s）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    print(f"[scheduler] 已注册 worldcup26.ir 轮询任务，间隔 {interval}s")

    # B2 配套：每 30 分钟回填各队 recent_form（比赛日期间足够）
    scheduler.add_job(
        _job_recent_form_backfill,
        trigger=IntervalTrigger(minutes=30),
        args=[session_factory],
        id="recent_form_backfill",
        name="B2 recent_form 回填（每 30 分钟）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    print("[scheduler] 已注册 B2 recent_form 回填任务，间隔 30 分钟")

    # B3: 小组赛结束后自动重算 Bracket（R32 对阵落位）
    scheduler.add_job(
        _job_bracket_auto_rebuild,
        trigger=IntervalTrigger(minutes=15),
        args=[session_factory],
        id="bracket_auto_rebuild",
        name="Bracket 自动重算（每 15 分钟，小组赛结束后）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    print("[scheduler] 已注册 Bracket 自动重算任务，间隔 15 分钟")

    # v0.5.1: 6h 周期刷新 — odds 快照打点 + 可选 football-data.co 元数据更新
    hours = max(settings.periodic_refresh_interval_hours, 1)
    scheduler.add_job(
        _job_periodic_refresh,
        trigger=IntervalTrigger(hours=hours),
        args=[session_factory],
        id="periodic_6h_refresh",
        name=f"6h 周期刷新（每 {hours}h：odds 快照 + fb-data 元数据）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    print(f"[scheduler] 已注册 6h 周期刷新任务，间隔 {hours}h")

    # v0.6.0: 预测日志自动结算 - 每 15 分钟扫描已完赛比赛, 写实际结果到 prediction_log
    scheduler.add_job(
        _job_settle_predictions,
        trigger=IntervalTrigger(minutes=15),
        args=[session_factory],
        id="settle_predictions",
        name="预测日志自动结算（每 15 分钟）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    print("[scheduler] 已注册 预测日志自动结算 任务，间隔 15 分钟")

    # v0.7.1.1: MC 缓存预热 - 每 6h 确保默认参数组合有缓存
    scheduler.add_job(
        _job_mc_cache_warmup,
        trigger=IntervalTrigger(hours=6),
        args=[session_factory],
        id="mc_cache_warmup",
        name="MC 缓存预热（每 6h: blend/10000/seed=42）",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    print("[scheduler] 已注册 MC 缓存预热任务，间隔 6h")


def _job_recent_form_backfill(session_factory: Callable) -> None:
    """定时回填 B2 近期状态因子."""
    from app.services.recent_form import compute_and_persist_recent_form  # 避免循环 import

    db: Session = session_factory()
    try:
        result = compute_and_persist_recent_form(db, lookback=5)
        print(
            f"[{datetime.now().isoformat()}] B2 recent_form 回填: "
            f"{result['teams_updated']} 队更新，{result['teams_with_data']} 队有数据"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now().isoformat()}] B2 recent_form 回填失败: {exc}")
    finally:
        db.close()


def _job_bracket_auto_rebuild(session_factory: Callable) -> None:
    """定时检测小组赛是否结束，结束后自动重算 Bracket.

    依赖 bracket_logic.should_auto_rebuild 做无状态判断，避免重复触发。
    """
    from app.services.bracket_logic import rebuild_bracket, should_auto_rebuild  # 避免循环 import

    db: Session = session_factory()
    try:
        if not should_auto_rebuild(db):
            return
        result = rebuild_bracket(db)
        print(
            f"[{datetime.now().isoformat()}] Bracket 自动重算: "
            f"updated_matches={result['updated_matches']}, "
            f"group_stage_finished={result['group_stage_finished']}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now().isoformat()}] Bracket 自动重算失败: {exc}")
    finally:
        db.close()


def _job_periodic_refresh(session_factory: Callable) -> None:
    """v0.5.1 6h 周期刷新任务:odds 快照打点 + 可选 fb-data 元数据更新."""
    from app.services.periodic_refresh import run_periodic_refresh  # 避免循环 import

    db: Session = session_factory()
    try:
        result = run_periodic_refresh(db)
        print(
            f"[{datetime.now().isoformat()}] 6h 周期刷新: "
            f"snapshots_added={result.get('snapshots_added', 0)}, "
            f"fb_status={result.get('fb_status', 'unknown')}, "
            f"fb_matches_updated={result.get('fb_matches_updated', 0)}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now().isoformat()}] 6h 周期刷新失败: {exc}")
    finally:
        db.close()


def _job_settle_predictions(session_factory: Callable) -> None:
    """v0.6.0 预测日志自动结算 - 扫描已完赛比赛, 写 actual_outcome / brier / log_loss."""
    from app.services.prediction_log import settle_pending_predictions  # 避免循环 import

    db: Session = session_factory()
    try:
        count = settle_pending_predictions(db)
        if count > 0:
            print(f"[{datetime.now().isoformat()}] 预测日志结算: {count} 条")
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now().isoformat()}] 预测日志结算失败: {exc}")
    finally:
        db.close()


def _job_mc_cache_warmup(session_factory: Callable) -> None:
    """v0.7.1.1 MC 缓存预热 - 每 6h 为默认参数生成/刷新缓存."""
    from app.services.monte_carlo import run_mc_with_cache  # 避免循环 import

    db: Session = session_factory()
    try:
        result = run_mc_with_cache(
            db,
            n_sims=10000,
            model="blend",
            return_top_n=8,
            seed=42,
            refresh=False,
        )
        cached = result.get("cached", False)
        status = "hit" if cached else "miss(已重算并缓存)"
        print(f"[{datetime.now().isoformat()}] MC 缓存预热: {status}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{datetime.now().isoformat()}] MC 缓存预热失败: {exc}")
    finally:
        db.close()
