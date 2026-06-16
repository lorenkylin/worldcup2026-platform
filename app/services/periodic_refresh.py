"""v0.5.1 6h 周期刷新服务.

职责（scope 最小化原则）:
  1. 给所有现有 MatchOdds 追加 OddsSnapshot（即使值不变也记录，提供时间锚点）
  2. 可选：用 football-data.co 更新已有 match 元数据（status / score / kickoff_at）
     - 仅当配置 enabled + 有 api_key 时执行
     - 只更新已有比赛，不创建新比赛（避免与 wc26 主源冲突）

幂等性:
  - snapshot 同一 bookmaker + 同一秒（精度 1s）会被去重（防止重复打点）
  - fb-data 更新是 UPDATE 操作，多次执行结果一致

异常处理:
  - fb-data 调用失败 → 记录 ApiUsageLog status=error，snapshot 仍执行
  - 单个函数失败不影响另一个
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.models import ApiUsageLog, Match, MatchOdds, OddsSnapshot, Team


def take_odds_snapshots(db: Session) -> dict:
    """给所有现有 MatchOdds 追加 OddsSnapshot 快照(走势曲线打点).

    Returns:
        {"snapshots_added": N, "snapshots_skipped": M, "odds_total": T}
    """
    now = datetime.now(timezone.utc)
    odds_rows = db.query(MatchOdds).all()
    added = 0
    skipped = 0

    for odds in odds_rows:
        # 去重:同一 match + bookmaker + 同一秒 内已存在 snapshot 则跳过
        # 用 [now - 1s, now + 1s] 窗口查询避免精确时间戳冲突
        existing = (
            db.query(OddsSnapshot)
            .filter(
                OddsSnapshot.match_id == odds.match_id,
                OddsSnapshot.bookmaker == odds.bookmaker,
                OddsSnapshot.snapshot_at >= now - timedelta(seconds=2),
                OddsSnapshot.snapshot_at <= now + timedelta(seconds=2),
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        db.add(
            OddsSnapshot(
                match_id=odds.match_id,
                bookmaker=odds.bookmaker,
                home_win=odds.home_win,
                draw=odds.draw,
                away_win=odds.away_win,
                over_2_5=odds.over_2_5,
                under_2_5=odds.under_2_5,
                snapshot_at=now,
                source="periodic_6h",
            )
        )
        added += 1

    db.commit()
    return {
        "snapshots_added": added,
        "snapshots_skipped": skipped,
        "odds_total": len(odds_rows),
    }


def refresh_match_metadata_from_football_data(
    db: Session, client=None
) -> dict:
    """用 football-data.co 更新已有比赛元数据.

    仅当 settings.football_data_enabled=True 且 api_key 非空时执行.
    只更新已有比赛(status / home_score / away_score),不创建新比赛.
    时间范围:未来 7 天 + 过去 7 天(覆盖正在比赛和即将比赛).

    Args:
        db: SQLAlchemy Session.
        client: 可选 FootballDataClient(测试用 mock),生产传 None 内部创建.

    Returns:
        {"matches_updated": N, "matches_total_in_response": M,
         "fb_calls": C, "fb_calls_cached": CC, "status": "ok"/"skipped"/"error",
         "error": str or None}
    """
    if not settings.football_data_enabled:
        return {
            "matches_updated": 0,
            "matches_total_in_response": 0,
            "fb_calls": 0,
            "fb_calls_cached": 0,
            "status": "skipped",
            "reason": "football_data_enabled=False",
        }

    if not settings.football_data_api_key:
        return {
            "matches_updated": 0,
            "matches_total_in_response": 0,
            "fb_calls": 0,
            "fb_calls_cached": 0,
            "status": "skipped",
            "reason": "FOOTBALL_DATA_API_KEY 未配置",
        }

    # 客户端复用(测试可注入)
    if client is None:
        from app.services.football_data import FootballDataClient  # 避免循环

        client = FootballDataClient(
            api_key=settings.football_data_api_key,
            rate_limit_per_min=settings.football_data_rate_limit_per_min,
            cache_ttl_seconds=settings.football_data_cache_ttl_seconds,
            timeout_seconds=settings.football_data_timeout_seconds,
        )

    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        fb_matches = client.get_matches_by_date_range(date_from, date_to)
    except Exception as exc:
        # 记录到 ApiUsageLog
        db.add(
            ApiUsageLog(
                provider="football_data",
                endpoint=f"/matches?{date_from}~{date_to}",
                status="error",
                response_snippet=str(exc)[:200],
            )
        )
        db.commit()
        return {
            "matches_updated": 0,
            "matches_total_in_response": 0,
            "fb_calls": 1,
            "fb_calls_cached": 0,
            "status": "error",
            "error": str(exc)[:200],
        }

    # 更新已有比赛(fb 返回的 id 关联到我们的 match_odds → match)
    # 简化策略: 用 (homeTeam.name, awayTeam.name, utcDate.date) 模糊匹配
    updated = 0
    for fb in fb_matches:
        home_name = (fb.get("homeTeam") or {}).get("name", "")
        away_name = (fb.get("awayTeam") or {}).get("name", "")
        utc_date_str = fb.get("utcDate", "")
        if not (home_name and away_name and utc_date_str):
            continue

        # 解析 UTC 日期
        try:
            fb_date = datetime.fromisoformat(utc_date_str.replace("Z", "+00:00"))
            fb_date_only = fb_date.date()
        except ValueError:
            continue

        # 找本地 match（按 home_team.name_en + away_team.name_en + kickoff_at.date() 模糊匹配）
        # 用 aliased 避免两个 JOIN 同名表的歧义
        HomeTeam = aliased(Team)
        AwayTeam = aliased(Team)
        local_match = (
            db.query(Match)
            .join(HomeTeam, Match.home_team_id == HomeTeam.id)
            .join(AwayTeam, Match.away_team_id == AwayTeam.id)
            .filter(
                Match.kickoff_at >= datetime.combine(fb_date_only, datetime.min.time()),
                Match.kickoff_at < datetime.combine(fb_date_only + timedelta(days=1), datetime.min.time()),
            )
            .all()
        )
        # 用名称子串匹配(fb-data 可能用全称"Argentina",本地用"Argentina")
        matched = None
        for m in local_match:
            home_team_obj = db.query(Team).filter(Team.id == m.home_team_id).first()
            away_team_obj = db.query(Team).filter(Team.id == m.away_team_id).first()
            if (
                home_team_obj
                and away_team_obj
                and home_name.lower() in (home_team_obj.name_en or "").lower()
                and away_name.lower() in (away_team_obj.name_en or "").lower()
            ):
                matched = m
                break
        if not matched:
            continue

        # 仅当 fb-data 状态更新(比赛已结束/进行中)时更新 score
        fb_status = (fb.get("status") or "").upper()
        fb_score = fb.get("score") or {}
        full_time = fb_score.get("fullTime") or {}
        ft_home = full_time.get("home")
        ft_away = full_time.get("away")

        changed = False
        if fb_status == "FINISHED" and ft_home is not None and ft_away is not None:
            if matched.home_score != ft_home or matched.away_score != ft_away:
                matched.home_score = ft_home
                matched.away_score = ft_away
                matched.status = "finished"
                changed = True
        elif fb_status == "IN_PLAY" or fb_status == "LIVE":
            if matched.status != "live":
                matched.status = "live"
                changed = True

        if changed:
            updated += 1

    db.commit()

    # 记录调用成功
    db.add(
        ApiUsageLog(
            provider="football_data",
            endpoint=f"/matches?{date_from}~{date_to}",
            status="ok",
            response_snippet=f"updated={updated}, total={len(fb_matches)}",
        )
    )
    db.commit()

    return {
        "matches_updated": updated,
        "matches_total_in_response": len(fb_matches),
        "fb_calls": 1,
        "fb_calls_cached": 0,  # 简化:不暴露缓存命中细节
        "status": "ok",
    }


def run_periodic_refresh(db: Session, fb_client=None) -> dict:
    """编排 6h 周期刷新: snapshot + 可选 fb-data 更新.

    Args:
        db: SQLAlchemy Session.
        fb_client: 可选 FootballDataClient(测试用 mock).

    Returns:
        {
          "snapshots_added": N,
          "fb_status": "ok"/"skipped"/"error",
          "fb_matches_updated": N,
          "executed_at": ISO8601,
        }
    """
    result = {"executed_at": datetime.now(timezone.utc).isoformat()}

    # Step 1: odds snapshot 打点(总执行,即使 fb-data 失败也不影响)
    try:
        snap = take_odds_snapshots(db)
        result["snapshots_added"] = snap["snapshots_added"]
        result["snapshots_skipped"] = snap["snapshots_skipped"]
        result["odds_total"] = snap["odds_total"]
    except Exception as exc:
        result["snapshots_added"] = 0
        result["snapshots_error"] = str(exc)[:200]

    # Step 2: fb-data 元数据更新(可选)
    try:
        fb_result = refresh_match_metadata_from_football_data(db, client=fb_client)
        result["fb_status"] = fb_result["status"]
        result["fb_matches_updated"] = fb_result["matches_updated"]
        if fb_result["status"] == "error":
            result["fb_error"] = fb_result.get("error")
    except Exception as exc:
        result["fb_status"] = "error"
        result["fb_error"] = str(exc)[:200]

    # Step 3 (v0.7.0b): 自动写库 - 未来 7+1 天比赛 prediction_log 自动累积
    # 单条错误隔离, 不影响 snapshot/fb
    try:
        from app.services.prediction_log import auto_log_predictions  # 避免循环 import

        pl_result = auto_log_predictions(db)
        result["predictions_added"] = pl_result["predictions_added"]
        result["predictions_skipped"] = pl_result["predictions_skipped"]
        result["predictions_by_model"] = pl_result["by_model"]
        if pl_result["errors"]:
            result["predictions_errors"] = pl_result["errors"][:5]  # 截断,避免日志爆
    except Exception as exc:
        result["predictions_status"] = "error"
        result["predictions_error"] = str(exc)[:200]

    return result
