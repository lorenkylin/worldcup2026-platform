"""数据同步端点（手动触发）.

多源路线（v0.14.0）：
- 主源：API-Football 免费层（需 key，默认关闭）
- 备份源：worldcup26.ir（无需 key）→ worldcupstats.football（爬虫）
- 低频增强：football-data.org（默认关闭）
- 兜底：手动录入（admin 后台）
"""

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, SessionLocal
from app.services.multi_source_sync import full_sync as multi_source_full_sync
from app.services.multi_source_sync import live_sync as multi_source_live_sync
from app.services.h2h_backfill import backfill_h2h_history
from app.services.recent_form import compute_and_persist_recent_form
from app.services.stadium_geo import fill_stadium_coordinates
from app.services.multi_source_arbitration import preview_arbitration


router = APIRouter()


def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    """校验管理员 Token（常量时间比较，防止定时攻击）.

    当未配置 admin_token 时默认关闭管理端点，避免空 token 被绕过。
    """
    if not settings.admin_token or not hmac.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=403, detail="管理员 Token 无效")


@router.post("/full")
def sync_full(
    _: None = Depends(verify_admin_token),
) -> dict:
    """一键全量同步（API-Football 优先，失败回退 worldcup26.ir）.

    同步范围：球队、球场、赛程、比分、积分榜、事件。
    建议 6h 调用一次，或由 6h 周期调度器自动执行。
    """
    db = SessionLocal()
    try:
        result = multi_source_full_sync(db)
        return {"ok": bool(result.get("ok")), "synced_at": result["synced_at"], "summary": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"同步失败：{str(exc)[:500]}")
    finally:
        db.close()


@router.post("/live")
def sync_live(
    _: None = Depends(verify_admin_token),
) -> dict:
    """一键轻量实时同步：比分/状态（API-Football 优先，失败回退 worldcup26.ir）.

    建议 15-20 分钟调用一次，或由调度器自动执行。
    """
    db = SessionLocal()
    try:
        result = multi_source_live_sync(db)
        return {"ok": bool(result.get("ok")), "synced_at": result["synced_at"], "summary": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"同步失败：{str(exc)[:500]}")
    finally:
        db.close()


@router.post("/worldcup26/full")
def sync_worldcup26_full(
    _: None = Depends(verify_admin_token),
) -> dict:
    """一键全量同步（兼容旧端点，实际调用多源编排器，API-Football 优先）."""
    return sync_full(_)


@router.post("/recent-form/backfill")
def backfill_recent_form(
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动触发 B2 recent_form 回填（不影响生产调度）.

    用例：
    - 比赛结果手工录入后立即生效
    - 调度器失效时人工补
    """
    db = SessionLocal()
    try:
        result = compute_and_persist_recent_form(db, lookback=5)
    finally:
        db.close()
    return {"ok": True, "summary": result}


@router.post("/stadium-coords/fill")
def fill_coords(
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动补全球场经纬度（无需 token 时可由 main.py 启动时自动调用）."""
    return fill_stadium_coordinates()


@router.post("/h2h/backfill")
def backfill_h2h(
    _: None = Depends(verify_admin_token),
) -> dict:
    """B3: 手动触发 H2H 历史交锋回填（idempotent — 重复调用安全）.

    场景：
    - 首次部署 → 灌入 2018/2022 世界杯种子数据（100+ 场）
    - 后续扩展友谊赛/欧洲杯数据时 → 追加新种子后再次调用
    """
    db = SessionLocal()
    try:
        result = backfill_h2h_history(db)
    finally:
        db.close()
    return {"ok": True, "summary": result}


@router.post("/worldcupstats/schedule")
def sync_worldcupstats_schedule(
    _: None = Depends(verify_admin_token),
) -> dict:
    """手动触发 worldcupstats 赛程抓取（备份源）.

    调用方：data/scraper.py → data/seed.py。
    """
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        ["python", "data/scraper.py"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"抓取失败：{result.stderr[:500]}",
        )
    return {
        "ok": True,
        "message": "赛程抓取完成（请随后执行 data/seed.py 重新入库）",
        "stdout": result.stdout[-500:],
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/backtest/run")
def run_backtest_endpoint(
    _: None = Depends(verify_admin_token),
    format: str = "json",  # "json" / "markdown"
) -> dict:
    """B6: 执行预测模型回测，输出 Brier Score + 准确率.

    用例：
    - 模型上线前自检
    - 调优 Elo/Form/H2H 权重后验证
    - 客户/老板拍板前出具"模型质量报告"

    Args:
        format: 返回格式，json 返回结构化数据，markdown 返回可读报告
    """
    from app.services.backtest import run_backtest, render_markdown_report

    db = SessionLocal()
    try:
        report = run_backtest(db, lookback=999)
    finally:
        db.close()

    if format == "markdown":
        return {
            "ok": True,
            "summary": {
                "n_matches": report.n_matches,
                "n_evaluated": report.n_evaluated,
                "n_skipped": report.n_skipped,
                "accuracy": round(report.accuracy, 4),
                "brier_score": round(report.brier_score, 4),
                "top1_recall": round(report.top1_recall, 4),
                "top2_recall": round(report.top2_recall, 4),
            },
            "report_markdown": render_markdown_report(report),
        }
    else:
        return {
            "ok": True,
            "summary": {
                "n_matches": report.n_matches,
                "n_evaluated": report.n_evaluated,
                "n_skipped": report.n_skipped,
                "accuracy": round(report.accuracy, 4),
                "brier_score": round(report.brier_score, 4),
                "top1_recall": round(report.top1_recall, 4),
                "top2_recall": round(report.top2_recall, 4),
                "mean_predicted_home": round(report.mean_predicted_home, 4),
                "actual_home_freq": round(report.actual_home_freq, 4),
            },
            "predictions_sample": report.predictions[:10],
        }


@router.get("/arbitration")
def sync_arbitration_preview(
    _: None = Depends(verify_admin_token),
) -> dict:
    """多源字段级仲裁预览（只读，不写库）.

    同时拉取 API-Football 与 worldcup26.ir 的原始数据，
    按字段置信度做仲裁，返回每场比赛的字段决策与冲突情况。
    """
    db = SessionLocal()
    try:
        result = preview_arbitration(db)
        return {"ok": True, "previewed_at": datetime.now(timezone.utc).isoformat(), "summary": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"仲裁预览失败：{str(exc)[:500]}")
    finally:
        db.close()


@router.get("/status")
def sync_status_endpoint(
    _: None = Depends(verify_admin_token),
) -> dict:
    """同步配置与数据源状态."""
    return {
        "data_strategy": "multi-source / free-first",
        "primary_source": "api-football (free tier, 100 req/day)",
        "primary_source_enabled": settings.api_football_enabled
        and bool(settings.api_football_key or settings.rapidapi_key),
        "backup_sources": ["worldcup26.ir", "worldcupstats.football"],
        "enhance_source": "football-data.org (free tier, default off)",
        "fallback": "manual entry via /api/admin/* endpoints",
        "sync_interval_seconds": settings.sync_interval_seconds,
        "scheduler_running": True,
    }
