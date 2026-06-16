"""FastAPI 应用入口.

提供 RESTful API 与静态 H5 前端文件服务。
启动时同时启动 APScheduler 自动轮询（零预算纯免费源）。
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
from app.routers import matches, teams, groups, predictions, admin, admin_sync, admin_odds, simulator, elo, h2h, bracket, odds, health
from app.services.worldcup26_sync import full_sync as worldcup26_full_sync
from app.services.scheduler import build_default_jobs
from app.services.stadium_geo import fill_stadium_coordinates
from app.services.recent_form import compute_and_persist_recent_form
from app.services.h2h_backfill import backfill_h2h_history
from app.services.periodic_refresh import run_periodic_refresh as periodic_6h_refresh


# 创建数据表（首次启动时）
Base.metadata.create_all(bind=engine)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 0.110+ lifespan 上下文：启动/关闭调度器."""
    # 启动时
    if not scheduler.running:
        scheduler.start()
        build_default_jobs(scheduler, SessionLocal, worldcup26_full_sync)
        fill_stadium_coordinates()
        # 启动时立即跑一次 worldcup26.ir 同步（避免 15min 调度窗口期内数据 stale）
        try:
            db = SessionLocal()
            try:
                start_result = worldcup26_full_sync(db)
                print(
                    f"[lifespan] worldcup26.ir 启动同步: "
                    f"teams={start_result['teams']} matches={start_result['matches']} "
                    f"standings={start_result['standings']}"
                )
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            print(f"[lifespan] worldcup26.ir 启动同步失败: {exc}")
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
    yield
    # 关闭时
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version="0.7.2",
    debug=settings.debug,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS：允许本地开发与 H5 跨域调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
app.include_router(admin.router, prefix="/api/admin", tags=["管理"])
app.include_router(admin_sync.router, prefix="/api/admin/sync", tags=["数据同步"])
app.include_router(admin_odds.router, prefix="/api/admin", tags=["赔率管理"])


# 静态前端文件
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def serve_index(request: Request) -> FileResponse:
    """根路径返回 H5 首页."""
    return FileResponse(static_dir / "index.html")


@app.get("/health", tags=["健康检查"])
async def health_check() -> dict:
    """服务健康检查."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": app.version,
        "data_source": "worldcup26.ir (primary) + worldcupstats.football (backup) + manual (fallback)",
        "sync_interval_seconds": settings.sync_interval_seconds,
    }
