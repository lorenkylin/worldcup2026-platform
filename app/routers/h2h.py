"""P1.3: 历史交锋（H2H）详情 API.

Endpoints:
  GET /api/h2h/{code1}/{code2}
      → 两队**所有**历史交锋的完整场次列表 + 胜负条聚合
      → 数据源：2026 已完赛 (current) + 2018/2022 世界杯种子 (history)
      → 用于前端 #/h2h/{code1}/{code2} 详情页

  GET /api/teams/{code}/h2h-opponents
      → 该队历史上有过交锋的所有对手（按对决数倒序）
      → 用于"未来扩展：球队详情页"展示 H2H 入口

设计原则：
- 与 elo.py 的 _query_h2h_for_boost 解耦：详情页需要**完整场次列表**，
  而 boost 函数只需要**聚合数据**（home_wins/away_wins/draws）。
- 数据归一：以 code1 视角看主客（home/away），方便前端直接渲染
- 时间倒序：最近的放最前面
"""
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Team, Match, H2HHistoricalMatch

router = APIRouter()


def _normalize_match(
    code1: str,
    raw_home_code: str,
    raw_away_code: str,
    raw_home_score: int,
    raw_away_score: int,
    match_date,
    competition: str,
    stage: str,
    source: str,
) -> Dict:
    """把任意主客方向的比赛归一为 code1 视角.

    Returns:
        {
            "match_date": ISO 字符串,
            "code1_score": int,  # code1 视角的进球
            "code2_score": int,
            "code1_won": bool,
            "code2_won": bool,
            "draw": bool,
            "is_code1_home": bool,  # code1 是否为主队
            "competition": str,
            "stage": str,
            "source": "current_2026" | "history_2018_2022",
        }
    """
    if raw_home_code == code1:
        code1_score, code2_score = raw_home_score, raw_away_score
        is_code1_home = True
    else:
        code1_score, code2_score = raw_away_score, raw_home_score
        is_code1_home = False
    return {
        "match_date": match_date.isoformat() if hasattr(match_date, "isoformat") else str(match_date),
        "code1_score": code1_score,
        "code2_score": code2_score,
        "code1_won": code1_score > code2_score,
        "code2_won": code1_score < code2_score,
        "draw": code1_score == code2_score,
        "is_code1_home": is_code1_home,
        "competition": competition,
        "stage": stage or "",
        "source": source,
    }


@router.get("/h2h/{code1}/{code2}")
def get_h2h_detail(
    code1: str,
    code2: str,
    db: Session = Depends(get_db),
) -> Dict:
    """P1.3: 两队完整历史交锋详情.

    Returns:
        {
            "code1": "BRA",
            "code2": "ARG",
            "code1_team": {...},  # 球队基本信息
            "code2_team": {...},
            "summary": {
                "code1_wins": int, "code2_wins": int, "draws": int, "total": int,
                "current_2026": int, "history": int
            },
            "matches": [  # 完整场次列表（按日期倒序）
                {
                    "match_date": "2022-12-18T00:00:00",
                    "code1_score": 3, "code2_score": 3,
                    "code1_won": False, "code2_won": False, "draw": True,
                    "is_code1_home": True,
                    "competition": "FIFA World Cup",
                    "stage": "Final (Argentina won 4-2 on pens)",
                    "source": "history_2018_2022",
                },
                ...
            ],
        }
    """
    code1_u = code1.upper()
    code2_u = code2.upper()
    if code1_u == code2_u:
        raise HTTPException(status_code=400, detail="code1 与 code2 不能相同")

    # 1. 球队信息（用于详情页头部）
    # P1.3 修复：支持"非 2026 参赛队"作为 H2H 对手
    # 背景：h2h_historical_matches 包含 2018+2022 世界杯种子，部分球队
    #       （CMR/CRC/DEN/ISL/PER/POL/RUS/SRB/WAL 共 9 队）未晋级 2026 世界杯
    #       但 h2h-opponents API 会列出这些队作为对决对手，详情页必须能正常显示
    team1 = db.query(Team).filter(Team.fifa_code == code1_u).first()
    team2 = db.query(Team).filter(Team.fifa_code == code2_u).first()
    if not team1 or not team2:
        # Fallback: 构造临时 dict（保证前端不 404）
        def _fallback(code: str) -> Dict:
            return {
                "fifa_code": code,
                "name_zh": code,  # 没中文名就显示代码
                "name_en": code,
                "flag_emoji": "🏳️",
                "group_name": None,
            }
        if not team1 and not team2:
            raise HTTPException(status_code=404, detail=f"球队 {code1_u} 与 {code2_u} 都不存在")
        # 部分缺失：替换缺失的为 fallback（保持原 Order: code1/code2）
        if not team1:
            team1 = type("T", (), _fallback(code1_u))()
        if not team2:
            team2 = type("T", (), _fallback(code2_u))()

    matches: List[Dict] = []

    # 2. 2026 已完赛（status=finished）
    past = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .all()
    )
    for m in past:
        h_code = m.home_team.fifa_code if m.home_team else None
        a_code = m.away_team.fifa_code if m.away_team else None
        if (h_code == code1_u and a_code == code2_u) or (h_code == code2_u and a_code == code1_u):
            # 阶段展示：优先 stage（"Round of 16"），其次 group_name（"A"/"B"）+ " 组"
            stage_label = m.stage or (f"Group {m.group_name}" if m.group_name else "Group")
            matches.append(
                _normalize_match(
                    code1_u, h_code, a_code,
                    m.home_score, m.away_score,
                    m.kickoff_at,  # Match 表用的是 kickoff_at（不是 match_date）
                    "2026 FIFA World Cup",  # Match 模型无 competition 字段
                    stage_label,
                    "current_2026",
                )
            )

    # 3. 2018/2022 世界杯种子
    hist = (
        db.query(H2HHistoricalMatch)
        .filter(
            ((H2HHistoricalMatch.home_fifa_code == code1_u) & (H2HHistoricalMatch.away_fifa_code == code2_u))
            | ((H2HHistoricalMatch.home_fifa_code == code2_u) & (H2HHistoricalMatch.away_fifa_code == code1_u))
        )
        .order_by(H2HHistoricalMatch.match_date.desc())
        .all()
    )
    for h in hist:
        matches.append(
            _normalize_match(
                code1_u,
                h.home_fifa_code, h.away_fifa_code,
                h.home_score, h.away_score,
                h.match_date,
                h.competition or "FIFA World Cup",
                h.stage or "",
                "history_2018_2022",
            )
        )

    # 4. 按日期倒序排序
    matches.sort(key=lambda x: x["match_date"], reverse=True)

    # 5. 聚合（基于 code1 视角）
    code1_wins = sum(1 for m in matches if m["code1_won"])
    code2_wins = sum(1 for m in matches if m["code2_won"])
    draws = sum(1 for m in matches if m["draw"])
    current_count = sum(1 for m in matches if m["source"] == "current_2026")
    history_count = sum(1 for m in matches if m["source"] == "history_2018_2022")

    return {
        "code1": code1_u,
        "code2": code2_u,
        "code1_team": {
            "fifa_code": team1.fifa_code,
            "name_zh": team1.name_zh,
            "name_en": team1.name_en,
            "flag_emoji": team1.flag_emoji,
            "group_name": team1.group_name,
        },
        "code2_team": {
            "fifa_code": team2.fifa_code,
            "name_zh": team2.name_zh,
            "name_en": team2.name_en,
            "flag_emoji": team2.flag_emoji,
            "group_name": team2.group_name,
        },
        "summary": {
            "code1_wins": code1_wins,
            "code2_wins": code2_wins,
            "draws": draws,
            "total": len(matches),
            "current_2026": current_count,
            "history": history_count,
        },
        "matches": matches,
    }


@router.get("/teams/{code}/h2h-opponents")
def get_team_h2h_opponents(
    code: str,
    db: Session = Depends(get_db),
) -> Dict:
    """P1.3 扩展: 球队所有历史交锋对手（按对决数倒序）.

    Returns:
        {
            "fifa_code": "BRA",
            "opponents": [
                {"fifa_code": "ARG", "name_zh": "阿根廷", "matches_count": 2},
                ...
            ]
        }

    用例: 未来在球队详情页 (#/team/{id}) 展示"历史交锋过 X 队"，
    链接到 #/h2h/{code}/{opponent_code}。
    """
    code_u = code.upper()
    team = db.query(Team).filter(Team.fifa_code == code_u).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"球队 {code_u} 不存在")

    opponent_count: Dict[str, int] = {}

    # 2026 已完赛
    past = (
        db.query(Match)
        .filter(
            Match.status == "finished",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
        )
        .all()
    )
    for m in past:
        h_code = m.home_team.fifa_code if m.home_team else None
        a_code = m.away_team.fifa_code if m.away_team else None
        if h_code == code_u and a_code and a_code != code_u:
            opponent_count[a_code] = opponent_count.get(a_code, 0) + 1
        elif a_code == code_u and h_code and h_code != code_u:
            opponent_count[h_code] = opponent_count.get(h_code, 0) + 1

    # 2018/2022 种子
    hist = (
        db.query(H2HHistoricalMatch)
        .filter(
            (H2HHistoricalMatch.home_fifa_code == code_u)
            | (H2HHistoricalMatch.away_fifa_code == code_u)
        )
        .all()
    )
    for h in hist:
        opp = h.away_fifa_code if h.home_fifa_code == code_u else h.home_fifa_code
        if opp and opp != code_u:
            opponent_count[opp] = opponent_count.get(opp, 0) + 1

    # 关联球队信息
    opponents = []
    for opp_code, cnt in sorted(opponent_count.items(), key=lambda x: -x[1]):
        opp_team = db.query(Team).filter(Team.fifa_code == opp_code).first()
        opponents.append({
            "fifa_code": opp_code,
            "name_zh": opp_team.name_zh if opp_team else opp_code,
            "name_en": opp_team.name_en if opp_team else "",
            "flag_emoji": opp_team.flag_emoji if opp_team else "🏳️",
            "matches_count": cnt,
        })

    return {
        "fifa_code": code_u,
        "opponents_count": len(opponents),
        "opponents": opponents,
    }
