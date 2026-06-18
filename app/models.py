"""SQLAlchemy ORM 模型定义.

覆盖世界杯核心实体：球队、球场、比赛、积分榜、事件、统计、API 配额日志。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Index
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
    # v0.13: name_en 加唯一约束，防止 seed/sync 产生重复球场
    name_en = Column(String(100), unique=True, nullable=False)
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


class MatchOdds(Base):
    """M3 比赛赔率（市场预期视角，与 Elo 预测对比）.

    - 来源：管理员手动录入、历史回测、API 接入（v0.5.1+）
    - 赔率格式：decimal（欧式），如 2.10 表示 1 元本金回报 2.10 元
    - 一场比赛可有多条赔率记录（不同博彩公司），通过 fetched_at 区分最新
    """

    __tablename__ = "match_odds"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    bookmaker = Column(String(50), nullable=False, default="avg_market")  # bet365/pinnacle/avg_market
    home_win = Column(Float, nullable=True)   # 主胜赔率
    draw = Column(Float, nullable=True)       # 平局赔率
    away_win = Column(Float, nullable=True)   # 客胜赔率
    over_2_5 = Column(Float, nullable=True)   # 大球 2.5 赔率
    under_2_5 = Column(Float, nullable=True)  # 小球 2.5 赔率
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String(20), default="manual")  # manual/history/api

    match = relationship("Match")


class OddsSnapshot(Base):
    """v0.5.1 单场比赛每家公司每个时间点的赔率快照（用于走势图表）.

    设计动机:
    - match_odds 表只保留"每家公司最新一条"
    - 走势图表需要历史时序数据 → 独立 snapshot 表
    - 6h 调度器自动给所有现有赔率追加 snapshot(即使值不变也记录,提供时间锚点)
    - 未来接入付费赔率 API 直接 INSERT 本表即可

    字段语义:
    - snapshot_at: 时间锚点（UTC），走势曲线 X 轴
    - source: 数据来源(snapshot 自动打点 / manual 管理员录入 / api 外部 API)
    - 复合索引 (match_id, bookmaker, snapshot_at) 加速单场单公司历史查询
    """

    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    bookmaker = Column(String(50), nullable=False, index=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    over_2_5 = Column(Float, nullable=True)
    under_2_5 = Column(Float, nullable=True)
    snapshot_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    source = Column(String(20), default="snapshot")  # snapshot/manual/api

    match = relationship("Match")


class TeamEloRating(Base):
    """M1 球队历史评分（多源聚合）—— 历史保留表.

    注(v0.13): 当前运行时代码直接使用 data/seed/hicruben/results.json 与
    data/seed/statsbomb/statsbomb_elo.json,不再读取本表。本表仅作为 M1 历史
    数据保留,供旧脚本/报告追溯,未来若接入"评分时间序列"功能可重新启用。

    字段语义：
    - team_id：teams.id 外键，48 支参赛队
    - as_of_date：评分生效日期（按月粒度）
    - rating：评分值（Elo 用 1500 基线；FIFA 排名 1-210）
    - rank：当月官方排名（1 表示世界第一；可为 NULL）
    - source：数据来源（wikipedia / fifa / elo）
    - scraped_at：爬取入库时间（UTC）
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


class PredictionLog(Base):
    """v0.6.0 预测日志 - 追踪每次预测 vs 实际, 自动计算准确率.

    字段语义:
    - match_id: 比赛 ID (外键)
    - model_version: 'v1_elo' | 'v2_elo_enhanced' | 'v3_glicko2'
    - predicted_at: 预测时戳 (UTC)
    - pred_home_win/draw/away_win: 3 个概率, sum=1
    - actual_home_score/away_score: 比赛完后回填
    - actual_outcome: 'home'|'draw'|'away'
    - predicted_outcome: 'H'|'D'|'A'
    - correct: 1=正确, 0=错, NULL=未结算
    - brier_score: (p-actual)² 3-class
    - log_loss: -log(p_actual)
    - elo_home/elo_away: 当时的 rating 快照 (用于复盘)

    查询模式:
    1. 全部已结算: WHERE correct IS NOT NULL
    2. 单场历史: WHERE match_id = ? AND model_version = ?
    3. 全局准确率: SELECT AVG(correct), COUNT(*), model_version GROUP BY

    索引:
    - (match_id, model_version): 单场单模型历史
    - (correct): 已结算筛选
    - (model_version, predicted_at): 按模型 + 时间窗口
    """

    __tablename__ = "prediction_log"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    model_version = Column(String(30), nullable=False, index=True)
    predicted_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    # 预测输出
    pred_home_win = Column(Float, nullable=False)
    pred_draw = Column(Float, nullable=False)
    pred_away_win = Column(Float, nullable=False)
    predicted_outcome = Column(String(1), nullable=False)  # H/D/A
    # 实际结果 (比赛完后回填)
    actual_home_score = Column(Integer, default=None)
    actual_away_score = Column(Integer, default=None)
    actual_outcome = Column(String(4), default=None)  # home/draw/away
    correct = Column(Integer, default=None, index=True)  # 1/0/NULL
    # 评估指标
    brier_score = Column(Float, default=None)
    log_loss = Column(Float, default=None)
    # 评分快照
    elo_home = Column(Integer, default=None)
    elo_away = Column(Integer, default=None)
    # 来源
    source = Column(String(20), default="hicruben")  # hicruben/statsbomb/glicko2
    settled_at = Column(DateTime, default=None)  # 结算时戳
    # v0.11 Forward-Testing 字段
    # is_live: True = 比赛开赛前由 scheduler/用户实时写入的预测
    #         False (default) = backfill 历史回填 (scripts/backfill_prediction_log.py)
    # 区分逻辑: 用 predicted_at vs match.kickoff_at, 预测在比赛前 = live
    # 但 0.7.0b lifespan startup 也写预测, 比赛前 < 7 天也算 live
    is_live = Column(Boolean, default=False, index=True)  # 区分 backfill vs live
    # snapshot_id: 同一比赛同模型多次预测的快照组 (如赛前 7d/3d/1d 多次预测)
    # 默认为 None, 表示该预测无快照组概念 (一次性写入)
    snapshot_group = Column(String(40), default=None, index=True)  # 关联多次预测

    match = relationship("Match")


class MCRunHistory(Base):
    """v0.7.1.1 Monte Carlo Tournament 结果缓存.

    设计动机:
    - simulate_full_tournament(10000 sims) 约 4s CPU 阻塞
    - 默认参数(model=blend, n_sims=10000, seed=42) 访问频次高
    - 用表缓存让第二次请求 < 50ms

    字段语义:
    - model/n_sims/seed: 缓存键
    - generated_at: UTC 时间戳,6h TTL  freshness 依据
    - *_distribution / top_*_matchups: JSON 字符串存 MC 输出
    - n_teams/n_groups/total_matches_per_sim: 元数据

    查询模式:
    - 查最新缓存: SELECT * FROM mc_run_history
                  WHERE model=? AND n_sims=? AND seed=?
                  ORDER BY generated_at DESC LIMIT 1
    - 覆盖写: INSERT OR REPLACE (SQLite) / upsert (其他 DB)

    索引:
    - (model, n_sims, seed, generated_at): 加速最新缓存查询
    """

    __tablename__ = "mc_run_history"

    id = Column(Integer, primary_key=True)
    model = Column(String(20), nullable=False, index=True)
    n_sims = Column(Integer, nullable=False, index=True)
    seed = Column(Integer, nullable=False, index=True)
    generated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    duration_seconds = Column(Float, nullable=False)

    champion_distribution = Column(Text, nullable=False)
    finalist_distribution = Column(Text, nullable=False)
    semifinalist_distribution = Column(Text, nullable=False)
    quarterfinalist_distribution = Column(Text, nullable=False)
    r16_distribution = Column(Text, nullable=False)
    r32_distribution = Column(Text, nullable=False)
    group_advance_probability = Column(Text, nullable=False)

    top_final_matchups = Column(Text, nullable=False)
    top_semifinal_matchups = Column(Text, nullable=False)

    n_teams = Column(Integer, nullable=False)
    n_groups = Column(Integer, nullable=False)
    total_matches_per_sim = Column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_mc_run_history_lookup", "model", "n_sims", "seed", "generated_at"),
        {"sqlite_autoincrement": True},
    )
