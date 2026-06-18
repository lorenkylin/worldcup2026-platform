"""worldcup26.ir 数据同步服务.

该源为免费、无需 key、含 104 场赛程/48 队/16 球场/12 组积分榜。
已实测可用：响应快、字段完整、维护活跃（v1.0.5 2026-06-12）。

数据流：API → 字段映射 → DB upsert → data_source = "worldcup26.ir"
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Match, MatchEvent, Stadium, Standing, Team, ApiUsageLog
from app.services import data_quality


BASE_URL = settings.worldcup26_base_url
TIMEOUT = float(getattr(settings, "worldcup26_timeout_seconds", 20))


def _to_bool(v) -> bool:
    """将 TRUE/true/1 等转换为 bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() in ("TRUE", "1", "YES")
    return bool(v)


def _to_int_or_none(v) -> Optional[int]:
    """转换为 int，失败返回 None."""
    if v is None:
        return None
    if isinstance(v, str):
        if v.strip().upper() in ("NULL", "N/A", "", "TBD"):
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None
    return int(v)


def _parse_local_date(date_str: str, stadium_tz: str = "UTC") -> Optional[datetime]:
    """解析 local_date 并转换为 UTC naive 存储.

    worldcup26.ir 的 `local_date` 是球场本地墙钟时间，需按 stadium.timezone
    解析为 aware datetime 后再转 UTC，最终去掉 tzinfo 存入 DB。
    """
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S"):
        try:
            local = datetime.strptime(date_str, fmt)
            return (
                local.replace(tzinfo=ZoneInfo(stadium_tz))
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
        except ValueError:
            continue
    return None


def _parse_scorers(scorers_str: str) -> list[str]:
    """解析 home_scorers/away_scorers 字符串（实际是 JSON 字符串）。

    示例：{"J. Quiñones 9'","R. Jiménez 67'"}（花括号包引号，是该源特殊格式）
    """
    if not scorers_str or scorers_str.strip().lower() in ("null", "[]", ""):
        return []
    # 先尝试标准 JSON
    try:
        return json.loads(scorers_str)
    except (json.JSONDecodeError, TypeError):
        pass
    # 兜底：花括号包引号的特殊 JSON 格式
    try:
        # 替换花括号为方括号
        s = scorers_str.strip()
        if s.startswith("{") and s.endswith("}"):
            s = "[" + s[1:-1] + "]"
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        # 最后兜底：按 , 分割
        return [x.strip().strip('"').strip(chr(0x201C)).strip(chr(0x201D)) for x in scorers_str.replace("{", "").replace("}", "").split(",") if x.strip()]


def _clean_player_name(raw: str) -> str:
    """清理球员名字：去掉 Unicode 引号、ASCII 引号、分钟标记.

    示例：'J. Quiñones 9' -> 'J. Quiñones'
    """
    import re
    s = raw.strip()
    # 去掉首尾 Unicode 引号 (U+201C 左双引号 / U+201D 右双引号) 和 ASCII 引号
    for quote in (chr(0x201C), chr(0x201D), '"', "'"):
        s = s.strip(quote)
    # 去掉末尾的分钟标记，例如 "9'"、"67'"、"90+3'"
    s = re.sub(r"\s*\d+\s*(?:\+\s*\d+\s*)?['′]?\s*$", "", s).strip()
    return s


def _extract_minute(scorer_text: str) -> int:
    """从 'J. Quiñones 9' 中提取分钟."""
    import re
    m = re.search(r"(\d+)\s*'", scorer_text)
    if m:
        return int(m.group(1))
    return 0


def _normalize_stadium_name(name: str) -> str:
    """球场名规范化：忽略尾部 Stadium 与大小写，用于兜底匹配.

    注意：只去尾部的 Stadium，保留 Field（如 GEHA Field at Arrowhead）。
    否则 "GEHA Field at Arrowhead Stadium" 与 "GEHA Field at Arrowhead"
    会被错误地匹配到不同 key，导致重复插入。
    """
    s = name.strip().lower()
    s = re.sub(r"\s+stadium\s*$", "", s)
    return s


def _normalize_country(country: str) -> str:
    """国家名规范化：处理 USA/United States 等变体，用于兜底匹配."""
    s = (country or "").strip().lower()
    if s in ("usa", "us", "united states of america"):
        return "united states"
    return s


def _cleanup_stale_rows(db: Session) -> dict:
    """同步后清理占位球队和 match_number 越界的孤儿比赛."""
    deleted = {"placeholder_teams": 0, "orphan_matches": 0}

    placeholder_ids = [
        r[0]
        for r in db.query(Team.id).filter(
            (Team.name_en.like("Team %")) | (Team.fifa_code.op("GLOB")("[A-L][1-8]"))
        ).all()
    ]
    if placeholder_ids:
        db.query(Match).filter(Match.home_team_id.in_(placeholder_ids)).update(
            {"home_team_id": None}, synchronize_session=False
        )
        db.query(Match).filter(Match.away_team_id.in_(placeholder_ids)).update(
            {"away_team_id": None}, synchronize_session=False
        )
        deleted["placeholder_teams"] = db.query(Team).filter(
            Team.id.in_(placeholder_ids)
        ).delete(synchronize_session=False)

    # 仅删除非手动的孤儿比赛（match_number 越界可能是占位/测试数据）
    # 手动录入的比赛（admin/data_source='manual'）保留，避免误删人工测试数据
    deleted["orphan_matches"] = db.query(Match).filter(
        (Match.data_source != "manual")
        & ((Match.match_number < 1) | (Match.match_number > 104))
    ).delete(synchronize_session=False)

    db.commit()
    return deleted


def fetch_json(path: str) -> Optional[dict]:
    """同步拉取 worldcup26.ir JSON 端点.

    Trace (v0.2.1 audit): wc26 端点偶发 5xx + SSL EOF (api_usage_log 错误率 3.7%,
    39/1056). scheduler 每 15min 自动重试，错误日志留作运维 trace，平台不修 wc26 端问题.
    """
    url = f"{BASE_URL}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
        db = SessionLocal()
        try:
            log = ApiUsageLog(
                provider="worldcup26.ir",
                endpoint=path,
                status="ok" if resp.status_code == 200 else "error",
                response_snippet=resp.text[:200],
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        db = SessionLocal()
        try:
            db.add(ApiUsageLog(provider="worldcup26.ir", endpoint=path, status="error", response_snippet=str(exc)[:200]))
            db.commit()
        finally:
            db.close()
    return None


def sync_teams(db: Session) -> int:
    """同步 48 支球队基础信息."""
    data = fetch_json("/get/teams")
    if not data:
        return 0
    teams_raw = data.get("teams", [])

    teams = data_quality.deduplicate(
        teams_raw,
        key_func=lambda t: (t.get("fifa_code") or "").upper() or None,
        keep="last",
    )
    data_quality.assert_unique(
        teams,
        key_func=lambda t: (t.get("fifa_code") or "").upper() or None,
        label="worldcup26.ir teams",
    )

    count = 0
    for t in teams:
        en_name = t.get("name_en", "").strip()
        if not en_name:
            continue
        # 优先用 fifa_code 作为唯一键
        team = db.query(Team).filter(Team.fifa_code == t.get("fifa_code", "")).first()
        if not team:
            team = Team(
                fifa_code=t.get("fifa_code", "")[:10] or en_name[:3].upper(),
                name_zh=en_name,  # 占位，v0.2 用统一映射表替换
                name_en=en_name,
                group_name=t.get("groups", ""),
                flag_emoji="",
            )
            db.add(team)
        else:
            team.name_en = en_name
            team.group_name = t.get("groups", team.group_name)
        count += 1
    db.commit()
    return count


def sync_stadiums(db: Session) -> int:
    """同步 16 座球场."""
    data = fetch_json("/get/stadiums")
    if not data:
        return 0
    stadiums_raw = data.get("stadiums", [])

    stadiums = data_quality.deduplicate(
        stadiums_raw,
        key_func=lambda s: (s.get("name_en") or "").strip() or None,
        keep="last",
    )
    data_quality.assert_unique(
        stadiums,
        key_func=lambda s: (s.get("name_en") or "").strip() or None,
        label="worldcup26.ir stadiums",
    )

    count = 0
    for s in stadiums:
        en_name = s.get("name_en", "").strip()
        city = s.get("city_en", "")
        country = s.get("country_en", "")
        if not en_name:
            continue
        # 1) 精确匹配 name_en（唯一约束后优先）
        stadium = db.query(Stadium).filter(Stadium.name_en == en_name).first()
        # 2) 兜底：同名变体（如 Arrowhead / Arrowhead Stadium）+ 同城市/国家
        #    国家做规范化，避免 DB 里是 "USA" 而 API 返回 "United States" 导致重复
        if stadium is None and city and country:
            target_key = _normalize_stadium_name(en_name)
            norm_country = _normalize_country(country)
            candidates = (
                db.query(Stadium)
                .filter(Stadium.city == city, Stadium.name_en != "")
                .all()
            )
            for cand in candidates:
                if (
                    _normalize_country(cand.country) == norm_country
                    and _normalize_stadium_name(cand.name_en) == target_key
                ):
                    stadium = cand
                    break
        if stadium is None:
            stadium = Stadium(
                name_zh=en_name,
                name_en=en_name,
                city=city,
                country=country,
            )
            db.add(stadium)
        else:
            stadium.city = city or stadium.city
            stadium.country = country or stadium.country
            # 若原 name_en 是旧/短名称，可更新为 API 返回的正式名
            if _normalize_stadium_name(stadium.name_en) == _normalize_stadium_name(en_name):
                stadium.name_en = en_name
        count += 1
    db.commit()
    return count


def sync_matches(db: Session) -> int:
    """同步 104 场比赛赛程与结果.

    Trace (v0.2.1 audit):
    - B-5 H2H 9 队 fallback: 9 个 fifa_code 不在 teams 表 (DEN/POL/RUS/SRB/WAL/CMR/CRC/ISL/PER,
      2018+2022 世界杯非参赛队) — h2h router 用 duck typing 临时对象兼容，平台不修.
    - B-6 standings 双路径: 本函数不调 _update_standing (admin.py 独有), 改由 sync_standings
      走独立 /get/groups 端点 (权威). 两路径不重复累加积分.
    """
    data = fetch_json("/get/games")
    if not data:
        return 0
    games_raw = data.get("games", [])

    # 使用前分析：去重 + 唯一性检查
    games = data_quality.deduplicate(
        games_raw,
        key_func=lambda g: str(_to_int_or_none(g.get("id")) or ""),
        keep="last",
    )
    data_quality.assert_unique(
        games,
        key_func=lambda g: str(_to_int_or_none(g.get("id")) or ""),
        label="worldcup26.ir games",
    )

    # 拉 wc26 teams 构建 wc26_id → fifa_code 映射（用于正确联表，避免 ID 错位）
    wc26_id_to_fifa: dict[int, str] = {}
    wc26_teams_data = fetch_json("/get/teams")
    if wc26_teams_data:
        for t in wc26_teams_data.get("teams", []):
            tid = _to_int_or_none(t.get("id"))
            fc = (t.get("fifa_code") or "").strip()
            if tid and fc:
                wc26_id_to_fifa[tid] = fc
    print(f"[sync_matches] wc26_id → fifa_code 映射 {len(wc26_id_to_fifa)} 条")

    # 拉 wc26 stadiums 构建 wc26_id → name_en 映射（用于 Stadium 联表）
    wc26_id_to_stadium_name: dict[int, str] = {}
    wc26_stadiums_data = fetch_json("/get/stadiums")
    if wc26_stadiums_data:
        for s in wc26_stadiums_data.get("stadiums", []):
            sid = _to_int_or_none(s.get("id"))
            sname = (s.get("name_en") or "").strip()
            if sid and sname:
                wc26_id_to_stadium_name[sid] = sname
    print(f"[sync_matches] wc26_id → stadium_name 映射 {len(wc26_id_to_stadium_name)} 条")

    count = 0
    now = data_quality.now_utc()
    for g in games:
        match_num = _to_int_or_none(g.get("id"))
        if match_num is None:
            continue

        match = db.query(Match).filter(Match.match_number == match_num).first()
        if not match:
            match = Match(match_number=match_num)
            db.add(match)

        # 数据源优先级保护：manual 永不覆盖；api-football 在 6h 内不覆盖
        if not data_quality.can_overwrite(
            match.data_source, "worldcup26.ir", match.last_updated_at
        ):
            continue

        # 球队 ID 映射：用 fifa_code 联表（wc26 的 team_id 跟我们的 teams.id 不一致）
        home_team_id = _to_int_or_none(g.get("home_team_id"))
        away_team_id = _to_int_or_none(g.get("away_team_id"))
        if home_team_id:
            home_fifa = wc26_id_to_fifa.get(home_team_id)
            if home_fifa:
                home = db.query(Team).filter(Team.fifa_code == home_fifa).first()
                if home:
                    match.home_team_id = home.id
                    match.home_team_placeholder = ""
        if away_team_id:
            away_fifa = wc26_id_to_fifa.get(away_team_id)
            if away_fifa:
                away = db.query(Team).filter(Team.fifa_code == away_fifa).first()
                if away:
                    match.away_team_id = away.id
                    match.away_team_placeholder = ""

        # 球场（用 name_en 联表，wc26 stadium_id 跟我们的 Stadium.id 不一致）
        stadium_wc26_id = _to_int_or_none(g.get("stadium_id"))
        stadium = None
        if stadium_wc26_id:
            stadium_name = wc26_id_to_stadium_name.get(stadium_wc26_id)
            if stadium_name:
                stadium = db.query(Stadium).filter(Stadium.name_en == stadium_name).first()
                if stadium:
                    match.stadium_id = stadium.id

        # 状态机保护
        is_finished = _to_bool(g.get("finished"))
        time_elapsed = g.get("time_elapsed", "")
        if is_finished:
            new_status = "finished"
        elif time_elapsed and time_elapsed not in ("", "scheduled", "notstarted"):
            new_status = "live"
        else:
            new_status = "scheduled"
        if not data_quality.is_status_transition_allowed(match.status, new_status):
            continue

        # 比分
        home_score = _to_int_or_none(g.get("home_score"))
        away_score = _to_int_or_none(g.get("away_score"))
        if home_score is not None:
            match.home_score = home_score
        if away_score is not None:
            match.away_score = away_score

        match.status = new_status
        match.time_elapsed = time_elapsed or match.time_elapsed or ""

        # 阶段与轮次
        match.stage = "小组赛" if g.get("type") == "group" else "淘汰赛"
        match.group_name = g.get("group", match.group_name) or match.group_name
        match.round_number = _to_int_or_none(g.get("matchday")) or match.round_number or 1

        # 开球时间：按球场本地时区解析后转 UTC 存储，并校验合理窗口
        stadium_tz = stadium.timezone if stadium else "UTC"
        kickoff = _parse_local_date(g.get("local_date", ""), stadium_tz)
        if kickoff and data_quality.validate_kickoff_window(
            kickoff.replace(tzinfo=timezone.utc), context=f"match {match_num}"
        ):
            match.kickoff_at = kickoff

        match.data_source = "worldcup26.ir"
        match.last_updated_at = now
        count += 1

    db.commit()

    # 同步事件（仅对已结束比赛，且未手工修改过）
    _sync_events_for_finished_matches(db, games)
    return count


def _sync_events_for_finished_matches(db: Session, games: list[dict]) -> int:
    """为已结束比赛同步进球事件（不覆盖人工录入）.

    Trace (v0.2.1 audit): B-3 — wc26 id=9 (CIV-ECU 1:0) home_scorers="null" 字符串,
    _parse_scorers('null') 正确返回 [], 该场比赛 events=0 (score 1:0 已从 home_score 写入).
    wc26 端未记录进球者属外部数据源问题, 平台不污染事件表写 placeholder.
    """
    count = 0
    for g in games:
        if not _to_bool(g.get("finished")):
            continue
        match_num = _to_int_or_none(g.get("id"))
        match = db.query(Match).filter(Match.match_number == match_num).first()
        if not match:
            continue
        # 若已有事件则跳过（避免重复写入，手工事件也视为有效）
        existing_keys = {
            f"{e.event_type}:{e.minute}:{e.player_name}"
            for e in db.query(MatchEvent).filter(MatchEvent.match_id == match.id).all()
        }

        def _event_key(scorer: str, team_id: Optional[int]) -> str:
            return f"goal:{_extract_minute(scorer)}:{_clean_player_name(scorer)}"

        home_scorers = data_quality.deduplicate(
            _parse_scorers(g.get("home_scorers", "")),
            key_func=lambda s: _event_key(s, match.home_team_id),
            keep="last",
        )
        for scorer in home_scorers:
            key = _event_key(scorer, match.home_team_id)
            if key in existing_keys:
                continue
            event = MatchEvent(
                match_id=match.id,
                team_id=match.home_team_id,
                event_type="goal",
                minute=_extract_minute(scorer),
                player_name=_clean_player_name(scorer),
                extra_info="worldcup26.ir 自动同步",
            )
            db.add(event)
            existing_keys.add(key)
            count += 1

        away_scorers = data_quality.deduplicate(
            _parse_scorers(g.get("away_scorers", "")),
            key_func=lambda s: _event_key(s, match.away_team_id),
            keep="last",
        )
        for scorer in away_scorers:
            key = _event_key(scorer, match.away_team_id)
            if key in existing_keys:
                continue
            event = MatchEvent(
                match_id=match.id,
                team_id=match.away_team_id,
                event_type="goal",
                minute=_extract_minute(scorer),
                player_name=_clean_player_name(scorer),
                extra_info="worldcup26.ir 自动同步",
            )
            db.add(event)
            existing_keys.add(key)
            count += 1

    db.commit()
    return count


def sync_standings(db: Session) -> int:
    """同步 12 组积分榜.

    关键点：wc26 /get/groups 的 team_id 是线性编号 1-48（按 A-L 组顺序），
    与我们 Team.id（SQLite 自增 + FIFA 抽签顺序）**不一致**。
    必须先做 wc26_id → fifa_code → 我们 Team.id 的映射，否则 18 队写错位。
    """
    data = fetch_json("/get/groups")
    if not data:
        return 0
    groups = data.get("groups", [])

    # 拉 wc26 teams 构建 wc26_id → fifa_code 映射（与 sync_matches 一致）
    wc26_id_to_fifa: dict[int, str] = {}
    wc26_teams_data = fetch_json("/get/teams")
    if wc26_teams_data:
        for t in wc26_teams_data.get("teams", []):
            tid = _to_int_or_none(t.get("id"))
            fc = (t.get("fifa_code") or "").strip()
            if tid and fc:
                wc26_id_to_fifa[tid] = fc
    print(f"[sync_standings] wc26_id → fifa_code 映射 {len(wc26_id_to_fifa)} 条")

    # 预加载我们 Team 表到字典：fifa_code → Team.id
    team_by_fifa: dict[str, int] = {
        (t.fifa_code or "").upper(): t.id
        for t in db.query(Team).all()
        if t.fifa_code
    }

    # 扁平化并去重
    entries: List[Tuple[str, int, dict]] = []
    for g in groups:
        group_name = g.get("name", "")
        for t in g.get("teams", []):
            wc26_id = _to_int_or_none(t.get("team_id"))
            if not wc26_id:
                continue
            # 关键映射：wc26_id → fifa_code → 我们的 Team.id
            fifa = wc26_id_to_fifa.get(wc26_id)
            if not fifa:
                print(f"[sync_standings] 跳过：wc26_id={wc26_id} 无 fifa_code 映射")
                continue
            team_id = team_by_fifa.get(fifa.upper())
            if not team_id:
                print(f"[sync_standings] 跳过：fifa={fifa} 不在 teams 表")
                continue
            entries.append((group_name, team_id, t))

    unique_entries = data_quality.deduplicate(
        entries,
        key_func=lambda e: f"{e[0]}:{e[1]}",
        keep="last",
    )
    data_quality.assert_unique(
        entries,
        key_func=lambda e: f"{e[0]}:{e[1]}",
        label="worldcup26.ir standings entries",
    )

    count = 0
    now = data_quality.now_utc()
    for group_name, team_id, t in unique_entries:
        standing = (
            db.query(Standing)
            .filter_by(group_name=group_name, team_id=team_id)
            .first()
        )
        if not standing:
            standing = Standing(group_name=group_name, team_id=team_id)
            db.add(standing)
        standing.played = _to_int_or_none(t.get("mp")) or 0
        standing.won = _to_int_or_none(t.get("w")) or 0
        standing.drawn = _to_int_or_none(t.get("d")) or 0
        standing.lost = _to_int_or_none(t.get("l")) or 0
        standing.goals_for = _to_int_or_none(t.get("gf")) or 0
        standing.goals_against = _to_int_or_none(t.get("ga")) or 0
        standing.points = _to_int_or_none(t.get("pts")) or 0
        standing.updated_at = now
        count += 1
    db.commit()
    return count


def full_sync(db: Optional[Session] = None) -> dict:
    """一键全量同步.

    Args:
        db: 可选的 SQLAlchemy Session。若传 None 则内部创建（admin 手动调用场景），
            传 db 则由调用方管理生命周期（scheduler 场景）。

    v0.10 新增: 同步成功/失败时自动写 sync_status (持久化 JSON),
    让主人通过 /health 或 Cockpit 看到数据新鲜度。
    """
    from app.services.sync_status import record_success, record_failure  # 避免循环

    owns_db = db is None
    if owns_db:
        db = SessionLocal()
    try:
        result = {
            "teams": sync_teams(db),
            "stadiums": sync_stadiums(db),
            "matches": sync_matches(db),
            "standings": sync_standings(db),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        # 同步后清理占位球队/孤儿比赛，结果不混入主 result 以保持可序列化
        _cleanup_stale_rows(db)
        record_success(result)
        return result
    except Exception as exc:
        record_failure(str(exc))
        raise
    finally:
        if owns_db:
            db.close()
