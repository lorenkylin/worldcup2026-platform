"""多源数据同步编排器（v0.14.0）.

优先级：
1. API-Football（免费层）— 主实时源
2. worldcup26.ir — 备份实时源
3. 手动数据（admin 后台）— 永不覆盖

所有同步入口都返回 dict，异常被捕获并写入 sync_status，不中断调度器。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Match
from app.services import data_quality, sync_status
from app.services.multi_source_arbitration import arbitrate_and_apply
from app.services.stadium_geo import fill_stadium_coordinates
from app.services.recent_form import compute_and_persist_recent_form


def _api_football_available() -> bool:
    """检查是否启用并配置了 API-Football（直接 key 或 RapidAPI key 均可）."""
    return bool(
        settings.api_football_enabled
        and (settings.api_football_key or settings.rapidapi_key)
    )


def _has_matches_in_window(db: Session, hours: int = 3) -> bool:
    """检查未来/过去 N 小时内是否有比赛，用于决定是否发起 API 调用."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)
    window_end = now + timedelta(hours=hours)
    count = (
        db.query(Match)
        .filter(Match.kickoff_at >= window_start, Match.kickoff_at <= window_end)
        .count()
    )
    return count > 0


def _api_football_quality_ok(api_result: Dict) -> bool:
    """评估 API-Football 返回数据质量，质量差时触发降级."""
    fixtures = api_result.get("fixtures", {})
    quality = fixtures.get("quality", {})
    total = quality.get("total", 0)
    duplicates = quality.get("duplicates", 0)
    not_found = fixtures.get("not_found", 0)
    updated = fixtures.get("updated", 0)

    if total == 0:
        return False
    # 重复率超过 5% 或绝对重复 >5 条视为不可靠
    if duplicates > 5 or (duplicates / total) > 0.05:
        return False
    # 超过一半比赛找不到本地映射，可能是联赛/赛季配置错误
    if not_found > 50:
        return False
    # 完全没有更新，可能是过期缓存
    if updated == 0 and not_found > 0:
        return False
    return True


def _post_sync_hook(db: Session) -> Dict:
    """同步后公共收尾：球场坐标 + 近期状态."""
    coords = fill_stadium_coordinates()
    form = compute_and_persist_recent_form(db, lookback=5)
    return {"stadium_coords": coords, "recent_form": form}


def full_sync(db: Session) -> Dict:
    """一键全量同步.

    v0.14.4 改进：API-Football 可用时，先同步非 match 数据，再与 worldcup26.ir
    做字段级仲裁；失败或未启用则降级 worldcup26.ir。
    再失败则记录失败并返回错误信息，不抛异常导致调度器中断。
    """
    result: Dict = {"synced_at": datetime.now(timezone.utc).isoformat()}

    if _api_football_available():
        try:
            from app.services import api_football_sync

            api_result = api_football_sync.sync_all(db)
            if not _api_football_quality_ok(api_result):
                raise data_quality.DataQualityError(
                    f"API-Football 数据质量不达标: {api_result.get('fixtures', {}).get('quality')}"
                )

            # v0.14.4: 字段级仲裁，用 API-Football 原始 fixtures + worldcup26.ir 数据
            # 仲裁 match 字段，并记录冲突
            arbitration = arbitrate_and_apply(
                db, api_fixtures=api_result.get("fixtures_raw", [])
            )

            hook = _post_sync_hook(db)
            result.update(
                {
                    "ok": True,
                    "primary_source": "api-football",
                    "api_football": api_result,
                    "arbitration": arbitration,
                    "hook": hook,
                }
            )
            sync_status.record_success(result)
            return result
        except Exception as exc:  # noqa: BLE001
            result["api_football_error"] = str(exc)[:500]
            result["fallback_to"] = "worldcup26.ir"

    # 降级到 worldcup26.ir
    try:
        from app.services.worldcup26_sync import full_sync as wc26_full_sync

        wc_result = wc26_full_sync(db)
        hook = _post_sync_hook(db)
        result.update(
            {
                "ok": True,
                "primary_source": "worldcup26.ir",
                "worldcup26": wc_result,
                "hook": hook,
            }
        )
        sync_status.record_success(result)
        return result
    except Exception as exc:  # noqa: BLE001
        result["worldcup26_error"] = str(exc)[:500]
        result["ok"] = False
        result["primary_source"] = "manual"
        sync_status.record_failure(str(exc)[:500])
        return result


def live_sync(db: Session) -> Dict:
    """轻量实时同步：比分/状态.

    v0.14.4 改进：
    - 若启用 API-Football 且未来/过去 3h 内有比赛，调用 fixtures 按日期刷新，
      再与 worldcup26.ir 做字段级仲裁。
    - 失败或未启用则降级 worldcup26.ir 全量同步。
    """
    result: Dict = {"synced_at": datetime.now(timezone.utc).isoformat()}

    if _api_football_available() and _has_matches_in_window(db, hours=3):
        try:
            from app.services import api_football_sync

            now = datetime.now(timezone.utc)
            date_from = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            date_to = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            fixtures_result = api_football_sync.sync_fixtures(
                db, date_from=date_from, date_to=date_to
            )
            if not _api_football_quality_ok({"fixtures": fixtures_result}):
                raise data_quality.DataQualityError(
                    f"API-Football 实时数据质量不达标: {fixtures_result.get('quality')}"
                )

            # v0.14.4: 字段级仲裁
            arbitration = arbitrate_and_apply(
                db, api_fixtures=fixtures_result.get("fixtures_raw", [])
            )

            result.update(
                {
                    "ok": True,
                    "primary_source": "api-football",
                    "api_football": {
                        "fixtures_updated": fixtures_result["updated"],
                        "fixtures_skipped": fixtures_result["skipped"],
                        "fixtures_not_found": fixtures_result["not_found"],
                        "quality": fixtures_result.get("quality", {}),
                    },
                    "arbitration": arbitration,
                }
            )
            sync_status.record_success(result)
            return result
        except Exception as exc:  # noqa: BLE001
            result["api_football_error"] = str(exc)[:500]
            result["fallback_to"] = "worldcup26.ir"
    elif _api_football_available():
        result["skip_reason"] = "no_matches_in_window"
        result["fallback_to"] = "worldcup26.ir"

    # 降级到 worldcup26.ir（保持原有 15min 轮询行为）
    try:
        from app.services.worldcup26_sync import full_sync as wc26_full_sync

        wc_result = wc26_full_sync(db)
        result.update(
            {
                "ok": True,
                "primary_source": "worldcup26.ir",
                "worldcup26": wc_result,
            }
        )
        sync_status.record_success(result)
        return result
    except Exception as exc:  # noqa: BLE001
        result["worldcup26_error"] = str(exc)[:500]
        result["ok"] = False
        sync_status.record_failure(str(exc)[:500])
        return result
