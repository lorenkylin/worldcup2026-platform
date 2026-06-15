"""Pydantic 数据模型（请求/响应 schema）."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    """球队输出模型."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fifa_code: str
    name_zh: str
    name_en: str
    group_name: str
    flag_emoji: str = ""
    fifa_rank: Optional[int] = None
    elo_rating: int = 1500
    recent_form_points: Optional[int] = None
    recent_goal_diff: Optional[int] = None


class StadiumOut(BaseModel):
    """球场输出模型."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name_zh: str
    name_en: str
    city: str
    country: str
    timezone: str = "America/New_York"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class MatchEventOut(BaseModel):
    """比赛事件输出模型."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    minute: int
    player_name: str = ""
    extra_info: str = ""
    team_id: Optional[int] = None


class MatchStatsOut(BaseModel):
    """比赛统计输出模型."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    possession: Optional[int] = None
    shots: Optional[int] = None
    shots_on_target: Optional[int] = None
    passes: Optional[int] = None
    pass_accuracy: Optional[int] = None
    fouls: Optional[int] = None
    corners: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None


class MatchOut(BaseModel):
    """赛程输出模型."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    match_number: int
    stage: str
    group_name: Optional[str] = None
    round_number: int
    kickoff_at: datetime
    home_team: Optional[TeamOut] = None
    away_team: Optional[TeamOut] = None
    home_team_placeholder: str = ""
    away_team_placeholder: str = ""
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: str = "scheduled"
    time_elapsed: str = ""
    stadium: Optional[StadiumOut] = None
    last_updated_at: datetime
    data_source: str = "manual"
    events: list[MatchEventOut] = []
    stats: list[MatchStatsOut] = []


class GroupStandingOut(BaseModel):
    """小组排名输出模型."""

    team: TeamOut
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0


class PredictionOut(BaseModel):
    """预测输出模型."""

    match_id: int
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    expected_home_goals: float
    expected_away_goals: float
    recommended_score: str
    stars: int
    reasons: list[str]
    # B3: H2H 历史交锋（如果有）
    h2h_summary: Optional[str] = None
    h2h_record: Optional[dict] = None  # {home_wins, away_wins, draws, sample}
    # B2: 近期状态（如果有）
    home_recent_form: Optional[str] = None  # "WWDWL"
    away_recent_form: Optional[str] = None
    # F2: 可解释性 - 各因子贡献拆分
    factors_breakdown: Optional[dict] = None
    disclaimer: str = "预测仅供参考，不构成投注建议。"


class ScoreUpdateIn(BaseModel):
    """手动比分更新输入模型."""

    home_score: int
    away_score: int
    status: str = "finished"  # scheduled / live / finished
    time_elapsed: str = ""


class EventCreateIn(BaseModel):
    """手动事件录入输入模型."""

    team_id: Optional[int] = None
    event_type: str
    minute: int
    player_name: str = ""
    extra_info: str = ""


class StatsCreateIn(BaseModel):
    """手动统计录入输入模型."""

    team_id: int
    possession: Optional[int] = None
    shots: Optional[int] = None
    shots_on_target: Optional[int] = None
    passes: Optional[int] = None
    pass_accuracy: Optional[int] = None
    fouls: Optional[int] = None
    corners: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
