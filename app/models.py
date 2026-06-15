"""SQLAlchemy ORM 模型定义.

覆盖世界杯核心实体：球队、球场、比赛、积分榜、事件、统计、API 配额日志。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db import Base


class Team(Base):
    """参赛球队."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    fifa_code = Column(String(10), unique=True, index=True, nullable=False)
    name_zh = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)
    group_name = Column(String(10), nullable=False)
    flag_emoji = Column(String(20), default="")
    fifa_rank = Column(Integer, default=None)
    elo_rating = Column(Integer, default=1500)
    # B2: 近期状态因子（最近 5 场国际比赛积分 0-15；3 胜 1 平 0 负）
    # 当为空时预测模型跳过此因子
    recent_form_points = Column(Integer, default=None)
    # B2 配套：最近 5 场进失球差（xG 代理），用于在理由中展示进攻状态
    recent_goal_diff = Column(Integer, default=None)

    home_matches = relationship("Match", foreign_keys="Match.home_team_id", back_populates="home_team")
    away_matches = relationship("Match", foreign_keys="Match.away_team_id", back_populates="away_team")


class Stadium(Base):
    """比赛球场."""

    __tablename__ = "stadiums"

    id = Column(Integer, primary_key=True, index=True)
    name_zh = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    country = Column(String(50), nullable=False)
    latitude = Column(Float, default=None)
    longitude = Column(Float, default=None)
    timezone = Column(String(50), default="America/New_York")


class Match(Base):
    """赛程与比赛."""

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    match_number = Column(Integer, unique=True, nullable=False)
    stage = Column(String(50), nullable=False)  # 小组赛 / 16强 / 8强 / 半决赛 / 季军 / 决赛
    group_name = Column(String(10), nullable=True)
    round_number = Column(Integer, default=1)  # 小组赛轮次 1-3
    kickoff_at = Column(DateTime, nullable=False)
    stadium_id = Column(Integer, ForeignKey("stadiums.id"), nullable=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    home_team_placeholder = Column(String(100), default="")
    away_team_placeholder = Column(String(100), default="")
    home_score = Column(Integer, default=None)
    away_score = Column(Integer, default=None)
    status = Column(String(20), default="scheduled")  # scheduled / live / finished
    time_elapsed = Column(String(20), default="")
    last_updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    data_source = Column(String(50), default="manual")

    stadium = relationship("Stadium")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_matches")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_matches")
    events = relationship("MatchEvent", back_populates="match", cascade="all, delete-orphan")
    stats = relationship("MatchStats", back_populates="match", cascade="all, delete-orphan")


class MatchEvent(Base):
    """比赛事件（进球/红黄牌/换人）."""

    __tablename__ = "match_events"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    event_type = Column(String(20), nullable=False)  # goal / yellow_card / red_card / substitution
    minute = Column(Integer, nullable=False)
    player_name = Column(String(100), default="")
    extra_info = Column(String(255), default="")  # 助攻、换下球员等
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    match = relationship("Match", back_populates="events")


class MatchStats(Base):
    """赛后基础统计."""

    __tablename__ = "match_stats"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    possession = Column(Integer, default=None)  # 百分比
    shots = Column(Integer, default=None)
    shots_on_target = Column(Integer, default=None)
    passes = Column(Integer, default=None)
    pass_accuracy = Column(Integer, default=None)
    fouls = Column(Integer, default=None)
    corners = Column(Integer, default=None)
    yellow_cards = Column(Integer, default=None)
    red_cards = Column(Integer, default=None)

    match = relationship("Match", back_populates="stats")


class Standing(Base):
    """小组赛积分榜（可按小组/球队更新）."""

    __tablename__ = "standings"

    id = Column(Integer, primary_key=True, index=True)
    group_name = Column(String(10), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    drawn = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    points = Column(Integer, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ApiUsageLog(Base):
    """API 调用配额日志."""

    __tablename__ = "api_usage_log"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False)
    endpoint = Column(String(255), default="")
    called_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String(20), default="ok")  # ok / error / throttled
    response_snippet = Column(Text, default="")


class PredictionCache(Base):
    """预测结果缓存（F1 优化）.

    - payload_json 存完整 PredictionOut 序列化，TTL 5 分钟
    - 旧字段保留以防回滚时数据丢失（实际写入用 payload_json）
    """

    __tablename__ = "prediction_cache"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    # F1: 完整 JSON 缓存（覆盖 reasons / h2h_summary / h2h_record / recent_form 等所有字段）
    payload_json = Column(Text, default="")
    # 元数据
    home_team_fingerprint = Column(String(64), default="")  # 用于缓存命中时校验源数据是否变更
    away_team_fingerprint = Column(String(64), default="")
    # F2: 预测因子拆解 JSON（base_rate / form / h2h / elo_diff / venue 等的原始值与权重）
    factors_breakdown = Column(Text, default="")
    # 旧字段（仅作 fallback，未来清理）
    home_win_prob = Column(Float, default=0.0)
    draw_prob = Column(Float, default=0.0)
    away_win_prob = Column(Float, default=0.0)
    expected_home_goals = Column(Float, default=0.0)
    expected_away_goals = Column(Float, default=0.0)
    recommended_score = Column(String(10), default="")
    stars = Column(Integer, default=0)
    reasons = Column(Text, default="")
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class H2HHistoricalMatch(Base):
    """B3 历史交锋（手动种子数据 + 2018/2022 世界杯等历史比赛）.

    与 matches 表解耦：这些比赛不在 2026 赛程里，但用作"两队历史交锋"参考。
    字段尽量精简：球队名/fifa_code（不强制外键，兼容种子更新） + 比分 + 日期 + 赛事。
    """

    __tablename__ = "h2h_historical_matches"

    id = Column(Integer, primary_key=True, index=True)
    home_fifa_code = Column(String(10), nullable=False, index=True)
    away_fifa_code = Column(String(10), nullable=False, index=True)
    home_score = Column(Integer, nullable=False)
    away_score = Column(Integer, nullable=False)
    match_date = Column(DateTime, nullable=False, index=True)
    competition = Column(String(50), default="FIFA World Cup")  # 例：FIFA World Cup / Friendly
    stage = Column(String(50), default="")  # 例：Group A / Final / Round of 16
    neutral_venue = Column(Boolean, default=True)  # 大赛一般中立场


class TeamEloRating(Base):
    """M1 球队历史评分（多源聚合）.

    字段语义：
    - team_id：teams.id 外键，48 支参赛队
    - as_of_date：评分生效日期（按月粒度）
    - rating：评分值（Elo 用 1500 基线；FIFA 排名 1-210）
    - rank：当月官方排名（1 表示世界第一；可为 NULL）
    - source：数据来源（wikipedia / fifa / elo）
    - scraped_at：爬取入库时间（UTC）

    查询模式：找某场比赛日 T 之前最近的 (team_id, source) 评分。
    索引：team_id + as_of_date 复合索引加速"截至 T 的最近评分"查询。
    """

    __tablename__ = "team_elo_ratings"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    as_of_date = Column(DateTime, nullable=False, index=True)
    rating = Column(Float, nullable=False)
    rank = Column(Integer, default=None)
    source = Column(String(20), nullable=False, default="wikipedia")  # wikipedia/fifa/elo
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    team = relationship("Team")
