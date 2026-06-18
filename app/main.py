"""FastAPI 应用入口.

提供 RESTful API 与静态 H5 前端文件服务。
启动时同时启动 APScheduler 自动轮询（多源：API-Football 优先，worldcup26.ir 兜底）。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import engine, Base, SessionLocal
from app.routers import matches, teams, groups, predictions, admin, admin_sync, admin_odds, simulator, elo, h2h, bracket, odds, health, cockpit
from app.services.multi_source_sync import full_sync as multi_source_full_sync
from app.services.scheduler import build_default_jobs
from app.services.stadium_geo import fill_stadium_coordinates
from app.services.recent_form import compute_and_persist_recent_form
from app.services.h2h_backfill import backfill_h2h_history
from app.services.periodic_refresh import run_periodic_refresh as periodic_6h_refresh


APP_VERSION = "0.15.0"


def _get_version(fallback: str = APP_VERSION) -> str:
    """返回当前应用版本号.

    历史逻辑曾从 git tag 读取，但本地 tag 滞后时会导致版本显示错误；
    现在以显式常量为主，部署时可通过环境变量或 CI 注入覆盖。
    """
    import os
    return os.environ.get("WC26_VERSION", fallback)


# 创建数据表（首次启动时）
Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 0.110+ lifespan 上下文：启动/关闭调度器."""
    # 启动时
    if not scheduler.running:
        scheduler.start()
        build_default_jobs(scheduler, SessionLocal)
        fill_stadium_coordinates()
        # v0.14.2: 生产部署可设置 SKIP_STARTUP_SYNC=true，避免启动时全量同步/回填拖慢或失败
        if not settings.skip_startup_sync:
            # v0.14.0: 启动时立即跑一次多源全量同步（API-Football 优先，失败回退 worldcup26.ir）
            try:
                db = SessionLocal()
                try:
                    start_result = multi_source_full_sync(db)
                    print(
                        f"[lifespan] 多源启动同步: "
                        f"source={start_result.get('primary_source', 'unknown')} "
                        f"ok={start_result.get('ok')}"
                    )
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[lifespan] 多源启动同步失败: {exc}")
            # 启动时也跑一次 B2 回填（保证首次访问就有 form 数据）
            try:
                db = SessionLocal()
                try:
                    result = compute_and_persist_recent_form(db, lookback=5)
                    print(f"[lifespan] B2 recent_form 启动回填: {result['teams_updated']} 队更新")
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[lifespan] B2 recent_form 启动回填失败: {exc}")
            # B3: 启动时灌入 2018/2022 世界杯 H2H 历史交锋数据
            try:
                db = SessionLocal()
                try:
                    h2h_result = backfill_h2h_history(db)
                    print(f"[lifespan] B3 H2H 启动回填: 新增 {h2h_result['inserted']} 场，跳过 {h2h_result['skipped']} 场")
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[lifespan] B3 H2H 启动回填失败: {exc}")
            # v0.5.1: 启动时立即跑一次 6h 周期刷新（odds 快照 + 可选 fb-data）
            try:
                db = SessionLocal()
                try:
                    pr_result = periodic_6h_refresh(db)
                    print(
                        f"[lifespan] 6h 周期刷新启动: "
                        f"snapshots_added={pr_result.get('snapshots_added', 0)}, "
                        f"fb_status={pr_result.get('fb_status', 'unknown')}"
                    )
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[lifespan] 6h 周期刷新启动失败: {exc}")
            # v0.7.0b: 启动时立即跑一次 prediction_log 自动写库
            # 配合 6h 周期刷新,实盘预测自动累积,准确率统计持续滚雪球
            try:
                db = SessionLocal()
                try:
                    from app.services.prediction_log import auto_log_predictions

                    pl_result = auto_log_predictions(db)
                    print(
                        f"[lifespan] v0.7.0b prediction_log 启动回填: "
                        f"scanned={pl_result['matches_scanned']}, "
                        f"added={pl_result['predictions_added']}, "
                        f"skipped={pl_result['predictions_skipped']}, "
                        f"errors={len(pl_result['errors'])}"
                    )
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[lifespan] v0.7.0b prediction_log 启动回填失败: {exc}")
        else:
            print("[lifespan] SKIP_STARTUP_SYNC=true，跳过启动同步/回填，仅启动调度器")
    yield
    # 关闭时
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version=_get_version(),
    debug=settings.debug,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS：默认允许本地开发；生产通过 CORS_ORIGINS / CORS_ALLOW_CREDENTIALS 配置
# 当 origins 包含通配符时强制禁用 credentials，避免 opener/credential 泄露风险
_cors_allow_credentials = settings.cors_allow_credentials and "*" not in settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(matches.router, prefix="/api", tags=["赛程"])
app.include_router(teams.router, prefix="/api", tags=["球队"])
app.include_router(groups.router, prefix="/api", tags=["小组"])
app.include_router(predictions.router, prefix="/api", tags=["预测"])
app.include_router(simulator.router, prefix="/api", tags=["出线模拟"])
app.include_router(elo.router, prefix="/api", tags=["Elo 评级"])
app.include_router(h2h.router, prefix="/api", tags=["历史交锋"])
app.include_router(bracket.router, prefix="/api", tags=["淘汰赛"])
app.include_router(odds.router, prefix="/api", tags=["赔率"])
app.include_router(health.router, prefix="/api", tags=["健康检查"])
app.include_router(cockpit.router, prefix="/api", tags=["总览驾驶舱"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理"], include_in_schema=False)
app.include_router(admin_sync.router, prefix="/api/admin/sync", tags=["数据同步"], include_in_schema=False)
app.include_router(admin_odds.router, prefix="/api/admin", tags=["赔率管理"], include_in_schema=False)


# 静态前端文件
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/sw.js", include_in_schema=False)
async def serve_sw() -> FileResponse:
    """根路径 Service Worker 文件（确保 scope 为 /，可控制全站缓存）."""
    return FileResponse(static_dir / "sw.js", media_type="application/javascript")


@app.get("/", include_in_schema=False)
async def serve_index(request: Request) -> FileResponse:
    """根路径返回 H5 首页."""
    return FileResponse(static_dir / "index.html")


@app.get("/health", tags=["健康检查"])
async def health_check() -> dict:
    """服务健康检查 (v0.10 强化: 数据新鲜度 + DB 行数 + 调度器状态)."""
    from app.services.sync_status import get_status
    from sqlalchemy import func
    from app.models import Match, Team, Standing, PredictionLog, OddsSnapshot

    sync = get_status()
    # DB 行数 (快速聚合查询, < 100ms)
    try:
        db = SessionLocal()
        try:
            row_counts = {
                "matches": db.query(func.count(Match.id)).scalar() or 0,
                "teams": db.query(func.count(Team.id)).scalar() or 0,
                "standings": db.query(func.count(Standing.id)).scalar() or 0,
                "prediction_log": db.query(func.count(PredictionLog.id)).scalar() or 0,
                "odds_snapshots": db.query(func.count(OddsSnapshot.id)).scalar() or 0,
            }
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        row_counts = {"error": str(exc)}

    # 健康度聚合: fresh + scheduler_running = healthy; stale = degraded; critical = unhealthy
    freshness = sync.get("freshness", "unknown")
    if freshness == "fresh":
        overall = "healthy"
    elif freshness == "stale":
        overall = "degraded"
    elif freshness == "critical":
        overall = "unhealthy"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "app": settings.app_name,
        "version": app.version,
        "data_source": "api-football (primary, free tier) + worldcup26.ir (backup) + worldcupstats.football (backup) + manual (fallback)",
        "sync_interval_seconds": settings.sync_interval_seconds,
        "sync_status": sync,
        "db_row_counts": row_counts,
        "scheduler_running": scheduler.running,
    }
