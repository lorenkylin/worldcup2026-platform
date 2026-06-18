"""多源字段级仲裁协调器（v0.14.4）.

同时拉取 API-Football 和 worldcup26.ir 的原始数据，
对同一场比赛的每个字段做置信度仲裁，统一写回数据库。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Match, Stadium, Team
from app.services import data_quality
from app.services.api_football import ApiFootballClient
from app.services.api_football_sync import (
    _build_team_mapping,
    _default_client,
    extract_match_candidates_from_fixture,
)
from app.services.field_arbiter import (
    FIELD_CONFIDENCE,
    ArbitrationResult,
    FieldCandidate,
    arbitrate,
    log_conflicts,
)
from app.services.worldcup26_sync import (
    BASE_URL,
    TIMEOUT,
    _parse_local_date,
    _to_bool,
    _to_int_or_none,
    extract_match_candidates,
    fetch_json,
)

logger = logging.getLogger(__name__)


def _api_football_available() -> bool:
    """检查是否启用并配置了 API-Football."""
    return bool(
        settings.api_football_enabled
        and (settings.api_football_key or settings.rapidapi_key)
    )


def _fetch_api_football_fixtures(
    client: Optional[ApiFootballClient] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict]:
    """拉取 API-Football fixtures 原始数据."""
    if client is None:
        client = _default_client()
    if date_from is None:
        date_from = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    if date_to is None:
        date_to = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")
    try:
        return client.get_fixtures(
            date_from=date_from,
            date_to=date_to,
            league_id=settings.api_football_league_id,
            season=settings.api_football_season,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[multi_source_arbitration] API-Football fixtures 拉取失败: %s", exc)
        return []


def _fetch_worldcup26_games() -> List[Dict]:
    """拉取 worldcup26.ir games 原始数据."""
    data = fetch_json("/get/games")
    return data.get("games", []) if data else []


def _build_wc26_mappings(db: Session) -> Tuple[Dict[int, str], Dict[int, str]]:
    """构建 worldcup26.ir 的 team_id/stadium_id 映射."""
    wc26_id_to_fifa: Dict[int, str] = {}
    wc26_teams_data = fetch_json("/get/teams")
    if wc26_teams_data:
        for t in wc26_teams_data.get("teams", []):
            tid = _to_int_or_none(t.get("id"))
            fc = (t.get("fifa_code") or "").strip()
            if tid and fc:
                wc26_id_to_fifa[tid] = fc

    wc26_id_to_stadium_name: Dict[int, str] = {}
    wc26_stadiums_data = fetch_json("/get/stadiums")
    if wc26_stadiums_data:
        for s in wc26_stadiums_data.get("stadiums", []):
            sid = _to_int_or_none(s.get("id"))
            sname = (s.get("name_en") or "").strip()
            if sid and sname:
                wc26_id_to_stadium_name[sid] = sname

    return wc26_id_to_fifa, wc26_id_to_stadium_name


def _collect_candidates(
    db: Session,
    api_fixtures: List[Dict],
    wc26_games: List[Dict],
) -> Dict[int, List[FieldCandidate]]:
    """收集每场比赛的所有字段候选值."""
    candidates_by_match: Dict[int, List[FieldCandidate]] = {}

    # worldcup26.ir 候选值
    wc26_id_to_fifa, wc26_id_to_stadium_name = _build_wc26_mappings(db)
    deduped_games = data_quality.deduplicate(
        wc26_games,
        key_func=lambda g: str(_to_int_or_none(g.get("id")) or ""),
        keep="last",
    )
    for g in deduped_games:
        match_num = _to_int_or_none(g.get("id"))
        if match_num is None:
            continue
        match = db.query(Match).filter(Match.match_number == match_num).first()
        if not match:
            continue
        cands = extract_match_candidates(g, wc26_id_to_fifa, wc26_id_to_stadium_name, db)
        if cands:
            candidates_by_match.setdefault(match.id, []).extend(cands)

    # API-Football 候选值
    if api_fixtures:
        mapping = _build_team_mapping(db)
        deduped_fixtures = data_quality.deduplicate(
            api_fixtures,
            key_func=lambda item: str((item.get("fixture") or {}).get("id") or ""),
            keep="last",
        )
        for item in deduped_fixtures:
            match_id, cands = extract_match_candidates_from_fixture(item, mapping, db)
            if match_id and cands:
                candidates_by_match.setdefault(match_id, []).extend(cands)

    return candidates_by_match


def _apply_arbitration_result(db: Session, match: Match, result: ArbitrationResult) -> bool:
    """将仲裁结果写回 Match 表.

    Returns:
        是否有字段被修改。
    """
    now = data_quality.now_utc()
    modified = False

    # 静态字段：整体数据源权限检查（防止低优先级源覆盖高优先级静态权威数据）
    static_fields = {"home_team_id", "away_team_id", "stadium_id", "kickoff_at", "stage", "group_name", "round_number"}
    dynamic_fields = {"status", "time_elapsed", "home_score", "away_score"}

    winner_source = match.data_source or "manual"
    for field, decision in result.decisions.items():
        candidate_source = decision.source

        # manual 源永远胜出，但此处 decision.source 已经是 manual；
        # 仍需检查现有 Match.data_source 是否为 manual，若是则不允许自动源覆盖任何字段。
        if match.data_source == "manual" and candidate_source != "manual":
            continue

        if field in static_fields:
            if not data_quality.can_overwrite(match.data_source, candidate_source, match.last_updated_at):
                continue

        new_value = decision.value
        current_value = getattr(match, field, None)

        # 特殊业务校验
        if field == "status":
            if not data_quality.is_status_transition_allowed(match.status, new_value):
                continue
        if field == "kickoff_at":
            if not data_quality.validate_kickoff_window(new_value, context=f"match {match.match_number}"):
                continue
        if field in ("home_score", "away_score"):
            # 已结束比赛禁止比分回退到 None
            if match.status == "finished" and new_value is None:
                continue
            # 未开始比赛不应有比分
            if match.status == "scheduled" and new_value is not None:
                # 允许，因为可能状态同步比分同时到达；以状态字段为准
                pass

        if current_value != new_value:
            setattr(match, field, new_value)
            modified = True
            winner_source = candidate_source

    if modified:
        match.data_source = winner_source if winner_source != "manual" else match.data_source
        match.last_updated_at = now
        db.commit()

    return modified


def arbitrate_and_apply(
    db: Session,
    api_fixtures: Optional[List[Dict]] = None,
    wc26_games: Optional[List[Dict]] = None,
    client: Optional[ApiFootballClient] = None,
) -> Dict:
    """拉取（或接收）多源数据，做字段级仲裁并写库.

    Args:
        db: SQLAlchemy Session。
        api_fixtures: 可选，已拉取的 API-Football fixtures 原始数据。
        wc26_games: 可选，已拉取的 worldcup26.ir games 原始数据。
        client: 可选 API-Football 客户端。

    Returns:
        {"arbitrated_matches": N, "conflicts": N, "source": "multi-source-arbitration"}
    """
    if api_fixtures is None and _api_football_available():
        api_fixtures = _fetch_api_football_fixtures(client)
    if wc26_games is None:
        wc26_games = _fetch_worldcup26_games()

    if not api_fixtures and not wc26_games:
        return {"arbitrated_matches": 0, "conflicts": 0, "source": "multi-source-arbitration"}

    candidates_by_match = _collect_candidates(db, api_fixtures or [], wc26_games or [])

    arbitrated = 0
    all_conflicts: List[Dict] = []
    for match_id, candidates in candidates_by_match.items():
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match:
            continue

        result = arbitrate(match.match_number, candidates, current_status=match.status)
        if _apply_arbitration_result(db, match, result):
            arbitrated += 1
        all_conflicts.extend(result.conflicts)

    if all_conflicts:
        log_conflicts(all_conflicts)

    return {
        "arbitrated_matches": arbitrated,
        "conflicts": len(all_conflicts),
        "source": "multi-source-arbitration",
    }


def preview_arbitration(
    db: Session,
    api_fixtures: Optional[List[Dict]] = None,
    wc26_games: Optional[List[Dict]] = None,
    client: Optional[ApiFootballClient] = None,
) -> Dict:
    """拉取（或接收）多源数据，预览字段级仲裁结果（不写库）.

    Args:
        db: SQLAlchemy Session。
        api_fixtures: 可选，已拉取的 API-Football fixtures 原始数据。
        wc26_games: 可选，已拉取的 worldcup26.ir games 原始数据。
        client: 可选 API-Football 客户端。

    Returns:
        {
            "previewed_matches": N,
            "conflicts": N,
            "source": "multi-source-arbitration-preview",
            "matches": [ArbitrationResult.to_dict(), ...]
        }
    """
    if api_fixtures is None and _api_football_available():
        api_fixtures = _fetch_api_football_fixtures(client)
    if wc26_games is None:
        wc26_games = _fetch_worldcup26_games()

    if not api_fixtures and not wc26_games:
        return {
            "previewed_matches": 0,
            "conflicts": 0,
            "source": "multi-source-arbitration-preview",
            "matches": [],
        }

    candidates_by_match = _collect_candidates(db, api_fixtures or [], wc26_games or [])

    all_conflicts: List[Dict] = []
    match_results: List[Dict] = []
    for match_id, candidates in candidates_by_match.items():
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match:
            continue

        result = arbitrate(match.match_number, candidates, current_status=match.status)
        all_conflicts.extend(result.conflicts)
        match_results.append(result.to_dict())

    return {
        "previewed_matches": len(match_results),
        "conflicts": len(all_conflicts),
        "source": "multi-source-arbitration-preview",
        "matches": match_results,
    }
