"""API-Football 数据同步服务（v0.14.0）.

将 API-Football 的 fixtures/standings/events 映射到本地 ORM 模型.
匹配策略：用 (kickoff_at.date, home_fifa_code, away_fifa_code) 定位 Match，
不新增 DB 列。

手动录入的数据优先级最高（data_source == "manual" 时不覆盖比分/事件）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Match, MatchEvent, Standing, Team
from app.services import data_quality
from app.services.api_football import (
    ApiFootballClient,
    fifa_code_from_team_name,
    normalize_team_name,
)

# API-Football 短状态 → 本地 status
STATUS_SCHEDULED = {"NS", "TBD", "CANC", "POST", "SUSP", "INT", "ABD"}
STATUS_LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
STATUS_FINISHED = {"FT", "AET", "PEN", "AWD", "WO"}


def _default_client() -> ApiFootballClient:
    """从 settings 构造默认客户端."""
    return ApiFootballClient(
        api_key=settings.api_football_key,
        host=settings.api_football_host,
        rate_limit_per_min=settings.api_football_rate_limit_per_min,
        daily_limit=settings.api_football_daily_limit,
        cache_ttl_seconds=settings.api_football_cache_ttl_seconds,
        timeout_seconds=settings.api_football_timeout_seconds,
    )


def _build_team_mapping(db: Session) -> Dict[str, Team]:
    """构建 fifa_code → Team 映射（code 转大写）."""
    return {
        (t.fifa_code or "").upper(): t
        for t in db.query(Team).all()
        if t.fifa_code
    }


def _fifa_code_for_team(team_dict: Optional[Dict], mapping: Dict[str, Team]) -> Optional[str]:
    """从 API-Football 球队字典解析 FIFA code.

    优先使用返回的 code 字段（TLA），再用 name 别名/启发式匹配。
    """
    if not team_dict:
        return None
    code = (team_dict.get("code") or "").strip().upper()
    if code and code in mapping:
        return code
    # code 可能为空或与 FIFA code 不一致，尝试 name
    name = team_dict.get("name", "")
    alias = fifa_code_from_team_name(name)
    if alias and alias in mapping:
        return alias
    # 最后按 name_en 子串匹配
    norm = normalize_team_name(name)
    for fifa, team in mapping.items():
        if norm and (norm in normalize_team_name(team.name_en) or normalize_team_name(team.name_en) in norm):
            return fifa
    return None


def _map_status(short: str) -> str:
    """API-Football 短状态 → 本地 status."""
    s = (short or "").upper().strip()
    if s in STATUS_FINISHED:
        return "finished"
    if s in STATUS_LIVE:
        return "live"
    return "scheduled"


def _parse_fixture_date(date_str: Optional[str]) -> Optional[datetime]:
    """解析 API-Football UTC 时间字符串为 UTC aware datetime."""
    if not date_str:
        return None
    try:
        # 2026-06-11T19:00:00+00:00 或带 Z
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_teams(db: Session, client: Optional[ApiFootballClient] = None) -> Dict:
    """同步球队元数据（仅补充，不删除）.

    返回 {"updated": N, "skipped": N, "source": "api-football"}
    """
    if client is None:
        client = _default_client()

    mapping = _build_team_mapping(db)
    teams_raw = client.get_teams(
        league_id=settings.api_football_league_id,
        season=settings.api_football_season,
    )
    updated = 0
    skipped = 0
    for item in teams_raw:
        team_info = item.get("team") or item
        code = _fifa_code_for_team(team_info, mapping)
        if not code:
            skipped += 1
            continue
        team = mapping.get(code)
        if not team:
            skipped += 1
            continue
        name_en = (team_info.get("name") or "").strip()
        if name_en and not team.name_en:
            team.name_en = name_en
            updated += 1
        else:
            skipped += 1
    db.commit()
    return {"updated": updated, "skipped": skipped, "source": "api-football"}


def sync_fixtures(
    db: Session,
    client: Optional[ApiFootballClient] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict:
    """同步比赛赛程、比分与状态.

    返回 {
        "updated": N,
        "skipped": N,
        "not_found": N,
        "fixture_to_match": {fixture_id: match_id, ...},
        "source": "api-football",
    }
    """
    if client is None:
        client = _default_client()

    if date_from is None:
        date_from = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    if date_to is None:
        date_to = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")

    mapping = _build_team_mapping(db)
    fixtures_raw = client.get_fixtures(
        date_from=date_from,
        date_to=date_to,
        league_id=settings.api_football_league_id,
        season=settings.api_football_season,
    )

    # 1) 使用前分析：去重 + 唯一性检查 + 质量摘要
    fixtures = data_quality.deduplicate(
        fixtures_raw,
        key_func=lambda item: str((item.get("fixture") or {}).get("id") or ""),
        keep="last",
    )
    data_quality.assert_unique(
        fixtures,
        key_func=lambda item: str((item.get("fixture") or {}).get("id") or ""),
        label="api-football fixtures",
    )
    quality_summary = data_quality.source_quality_summary(
        fixtures_raw,
        key_func=lambda item: str((item.get("fixture") or {}).get("id") or ""),
    )

    updated = 0
    skipped = 0
    not_found = 0
    fixture_to_match: Dict[int, int] = {}
    now = data_quality.now_utc()

    for item in fixtures:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}

        fixture_id = fixture.get("id")
        if not fixture_id:
            continue

        home_team_dict = teams.get("home") or {}
        away_team_dict = teams.get("away") or {}
        home_code = _fifa_code_for_team(home_team_dict, mapping)
        away_code = _fifa_code_for_team(away_team_dict, mapping)
        if not home_code or not away_code:
            skipped += 1
            continue

        fixture_dt = _parse_fixture_date(fixture.get("date"))
        if not fixture_dt:
            skipped += 1
            continue

        # 2) 时间校对：开球时间必须在合理窗口内
        if not data_quality.validate_kickoff_window(fixture_dt, context=f"fixture {fixture_id}"):
            skipped += 1
            continue
        fixture_date = fixture_dt.date()

        # 匹配本地 Match：同一天 + 相同主客队
        match = (
            db.query(Match)
            .join(Team, Match.home_team_id == Team.id)
            .filter(
                Team.fifa_code == home_code,
                Match.kickoff_at >= datetime.combine(fixture_date, datetime.min.time()),
                Match.kickoff_at < datetime.combine(fixture_date + timedelta(days=1), datetime.min.time()),
            )
            .first()
        )
        if match:
            # 再校验 away_code
            away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
            if not away_team or (away_team.fifa_code or "").upper() != away_code:
                match = None

        if not match:
            not_found += 1
            continue

        fixture_to_match[int(fixture_id)] = int(match.id)

        # 3) 优先级与时间：手动/更高优先级源不覆盖（api-football 只覆盖 worldcup26.ir 或 6h 以上的旧数据）
        if not data_quality.can_overwrite(
            match.data_source, "api-football", match.last_updated_at
        ):
            skipped += 1
            continue

        # 4) 状态机保护：不允许 finished -> scheduled 等回退
        new_status = _map_status((fixture.get("status") or {}).get("short"))
        if not data_quality.is_status_transition_allowed(match.status, new_status):
            skipped += 1
            continue

        # 更新开球时间（API-Football 返回 UTC，直接覆盖）
        kickoff_utc = fixture_dt.replace(tzinfo=None)
        if match.kickoff_at != kickoff_utc:
            match.kickoff_at = kickoff_utc

        # 阶段/小组
        stage = "小组赛" if (item.get("league") or {}).get("round", "").startswith("Group") else "淘汰赛"
        if match.stage != stage:
            match.stage = stage

        # 比分与状态
        if match.status != new_status:
            match.status = new_status

        home_goals = goals.get("home")
        away_goals = goals.get("away")
        # goals 字段已结束/进行中比赛有值，未开始为 None
        if home_goals is not None and match.home_score != home_goals:
            match.home_score = int(home_goals)
        if away_goals is not None and match.away_score != away_goals:
            match.away_score = int(away_goals)

        if match.data_source != "api-football":
            match.data_source = "api-football"

        match.last_updated_at = now
        updated += 1

    db.commit()
    return {
        "updated": updated,
        "skipped": skipped,
        "not_found": not_found,
        "fixture_to_match": fixture_to_match,
        "source": "api-football",
        "quality": quality_summary,
    }


def sync_standings(
    db: Session,
    client: Optional[ApiFootballClient] = None,
) -> Dict:
    """同步小组积分榜.

    返回 {"updated": N, "skipped": N, "source": "api-football"}
    """
    if client is None:
        client = _default_client()

    mapping = _build_team_mapping(db)
    standings_raw = client.get_standings(
        league_id=settings.api_football_league_id,
        season=settings.api_football_season,
    )

    # 扁平化为 (group_name, team_id, entry) 列表，用于去重
    entries: List[Tuple[str, int, dict]] = []
    for league_block in standings_raw:
        league = league_block.get("league") or {}
        for group_idx, group_entries in enumerate(league.get("standings") or []):
            for entry in group_entries:
                team_info = entry.get("team") or {}
                code = _fifa_code_for_team(team_info, mapping)
                if not code:
                    continue
                team = mapping.get(code)
                if not team:
                    continue
                group_name = entry.get("group") or team.group_name or f"G{group_idx + 1}"
                if group_name.lower().startswith("group "):
                    group_name = group_name.split()[-1].upper()
                entries.append((group_name, team.id, entry))

    # 去重并检查重复
    unique_entries = data_quality.deduplicate(
        entries,
        key_func=lambda e: f"{e[0]}:{e[1]}",
        keep="last",
    )
    data_quality.assert_unique(
        entries,
        key_func=lambda e: f"{e[0]}:{e[1]}",
        label="api-football standings entries",
    )

    updated = 0
    skipped = len(entries) - len(unique_entries)
    now = data_quality.now_utc()
    for group_name, team_id, entry in unique_entries:
        standing = (
            db.query(Standing)
            .filter_by(group_name=group_name, team_id=team_id)
            .first()
        )
        if not standing:
            standing = Standing(group_name=group_name, team_id=team_id)
            db.add(standing)

        standing.played = entry.get("all", {}).get("played") or 0
        standing.won = entry.get("all", {}).get("win") or 0
        standing.drawn = entry.get("all", {}).get("draw") or 0
        standing.lost = entry.get("all", {}).get("lose") or 0
        standing.goals_for = entry.get("all", {}).get("goals", {}).get("for") or 0
        standing.goals_against = entry.get("all", {}).get("goals", {}).get("against") or 0
        standing.points = entry.get("points") or 0
        standing.updated_at = now
        updated += 1

    db.commit()
    return {"updated": updated, "skipped": skipped, "source": "api-football"}


def sync_events(
    db: Session,
    fixture_to_match: Dict[int, int],
    client: Optional[ApiFootballClient] = None,
) -> Dict:
    """同步比赛事件.

    仅处理已结束比赛且本地尚无事件记录的比赛，避免重复写入。
    返回 {"updated": N, "skipped": N, "source": "api-football"}
    """
    if client is None:
        client = _default_client()

    mapping = _build_team_mapping(db)
    updated = 0
    skipped = 0

    for fixture_id, match_id in fixture_to_match.items():
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match or match.status != "finished":
            skipped += 1
            continue
        # 若已有任何事件（含手工录入），跳过
        if db.query(MatchEvent).filter(MatchEvent.match_id == match_id).count() > 0:
            skipped += 1
            continue

        try:
            events_raw = client.get_events(fixture_id)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue

        # 去重：同一场同一分钟同类型同球员视为重复
        def _event_key(ev: dict) -> Optional[str]:
            ev_type = (ev.get("type") or "").lower()
            detail = (ev.get("detail") or "").lower()
            minute = (ev.get("time") or {}).get("elapsed", 0) or 0
            player = (ev.get("player") or {}).get("name", "")
            if not ev_type:
                return None
            return f"{ev_type}:{detail}:{minute}:{player}"

        events = data_quality.deduplicate(events_raw, key_func=_event_key, keep="last")

        # 查询该场比赛已存在的事件 key，避免 DB 重复
        existing_keys = {
            f"{e.event_type}:{e.minute}:{e.player_name}"
            for e in db.query(MatchEvent).filter(MatchEvent.match_id == match_id).all()
        }

        for ev in events:
            ev_type = (ev.get("type") or "").lower()
            detail = (ev.get("detail") or "").lower()
            minute = (ev.get("time") or {}).get("elapsed", 0) or 0
            team_dict = ev.get("team") or {}
            team_code = _fifa_code_for_team(team_dict, mapping)
            team_id = mapping.get(team_code).id if team_code and mapping.get(team_code) else None
            player = (ev.get("player") or {}).get("name", "")
            assist = (ev.get("assist") or {}).get("name", "")

            if ev_type == "goal":
                event_type = "goal"
            elif ev_type == "card":
                if "red" in detail:
                    event_type = "red_card"
                elif "yellow" in detail:
                    event_type = "yellow_card"
                else:
                    continue
            elif ev_type in ("subst", "substitution"):
                event_type = "substitution"
            else:
                continue

            db_key = f"{event_type}:{minute}:{player}"
            if db_key in existing_keys:
                continue

            extra = ""
            if event_type == "substitution" and assist:
                extra = f"换下: {assist}"
            elif event_type == "goal" and assist:
                extra = f"助攻: {assist}"

            db.add(
                MatchEvent(
                    match_id=match_id,
                    team_id=team_id,
                    event_type=event_type,
                    minute=int(minute),
                    player_name=player or "",
                    extra_info=extra or "API-Football 自动同步",
                )
            )
            existing_keys.add(db_key)
            updated += 1

    db.commit()
    return {"updated": updated, "skipped": skipped, "source": "api-football"}


def sync_all(db: Session, client: Optional[ApiFootballClient] = None) -> Dict:
    """一键全量同步 API-Football.

    返回结构化 summary，包含 teams/fixtures/standings/events 各阶段计数。
    """
    if client is None:
        client = _default_client()

    summary = {
        "source": "api-football",
        "teams": sync_teams(db, client),
    }
    fixture_result = sync_fixtures(db, client)
    summary["fixtures"] = {
        "updated": fixture_result["updated"],
        "skipped": fixture_result["skipped"],
        "not_found": fixture_result["not_found"],
    }
    summary["standings"] = sync_standings(db, client)
    summary["events"] = sync_events(db, fixture_result["fixture_to_match"], client)
    summary["synced_at"] = datetime.now(timezone.utc).isoformat()
    return summary
