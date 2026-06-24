"""B6 预测回测模块测试.

测试策略：
- 单元测试：纯 Brier Score 公式 + dataclass
- 集成测试：先注入 H2HHistoricalMatch 种子 + Team，运行 run_backtest
"""

import pytest
from datetime import datetime

from app.services.backtest import (
    run_backtest,
    render_markdown_report,
    BacktestReport,
    _predict_for_backtest,
)
from app.models import Team, H2HHistoricalMatch


# =============== 单元测试 ===============
def test_brier_score_perfect_prediction():
    """当预测概率与实际完全一致时，Brier 贡献为 0."""
    brier = (1.0 - 1) ** 2 + (0 - 0) ** 2 + (0 - 0) ** 2
    assert brier == 0.0


def test_brier_score_random_three_way():
    """三选一随机 (1/3, 1/3, 1/3) 实际主胜的 Brier ≈ 0.667."""
    brier = (1 / 3 - 1) ** 2 + (1 / 3 - 0) ** 2 + (1 / 3 - 0) ** 2
    assert abs(brier - 2 / 3) < 0.001


def test_backtest_result_dataclass():
    """BacktestReport dataclass 字段完整."""
    report = BacktestReport(
        n_matches=10,
        n_skipped=0,
        n_evaluated=10,
        accuracy=0.5,
        home_accuracy=0.6,
        draw_accuracy=0.3,
        away_accuracy=0.5,
        brier_score=0.55,
        brier_score_home=0.5,
        brier_score_draw=0.6,
        brier_score_away=0.5,
        mean_predicted_home=0.5,
        actual_home_freq=0.45,
        top1_recall=0.5,
        top2_recall=0.9,
        exact_score_accuracy=0.12,
        top3_score_recall=0.34,
        outcome_aligned_accuracy=0.13,
        primary_score_accuracy=0.10,
        secondary_score_accuracy=0.20,
    )
    assert report.n_matches == 10
    assert report.accuracy == 0.5
    assert report.brier_score == 0.55
    assert report.exact_score_accuracy == 0.12
    assert report.primary_score_accuracy == 0.10
    assert report.secondary_score_accuracy == 0.20


def test_render_markdown_report_contains_key_metrics():
    """Markdown 报告必须包含关键字段."""
    report = BacktestReport(
        n_matches=10,
        n_skipped=2,
        n_evaluated=8,
        accuracy=0.5,
        home_accuracy=0.6,
        draw_accuracy=0.3,
        away_accuracy=0.5,
        brier_score=0.55,
        brier_score_home=0.5,
        brier_score_draw=0.6,
        brier_score_away=0.5,
        mean_predicted_home=0.5,
        actual_home_freq=0.45,
        top1_recall=0.5,
        top2_recall=0.9,
        exact_score_accuracy=0.12,
        top3_score_recall=0.34,
        outcome_aligned_accuracy=0.13,
        primary_score_accuracy=0.10,
        secondary_score_accuracy=0.20,
    )
    md = render_markdown_report(report)
    assert "B6 预测模型回测报告" in md
    assert "Brier Score" in md
    assert "准确率" in md
    assert "评估 8" in md  # n_evaluated 显示在总比赛数列
    assert "精确比分命中" in md
    assert "首选比分命中" in md
    assert "次选比分命中" in md
    assert "Top3 比分召回" in md


# =============== 集成测试 ===============
@pytest.fixture
def seeded_eng_cro(db_session):
    """注入 ENG + CRO + 历史比赛样本（2018 半决赛）。"""
    from app.db import SessionLocal
    from app.models import Team, H2HHistoricalMatch

    # 真实数据：2018-07-11 世界杯半决赛 克罗地亚 2-1 英格兰
    eng = Team(
        id=100, fifa_code="ENG", name_zh="英格兰", name_en="England",
        group_name="K", flag_emoji="🏴", fifa_rank=5, elo_rating=1700,
    )
    cro = Team(
        id=101, fifa_code="CRO", name_zh="克罗地亚", name_en="Croatia",
        group_name="K", flag_emoji="🇭🇷", fifa_rank=10, elo_rating=1680,
    )
    hist = H2HHistoricalMatch(
        home_fifa_code="CRO", away_fifa_code="ENG",
        home_score=2, away_score=1,
        match_date=datetime(2018, 7, 11),
        competition="FIFA World Cup", stage="Semifinal", neutral_venue=True,
    )
    db_session.add_all([eng, cro, hist])
    db_session.commit()
    return {"eng": eng, "cro": cro, "hist": hist}


def test_backtest_integration_with_seed_data(db_session, seeded_eng_cro):
    """真实种子 + 球队注入 → 回测应有 1 场评估."""
    report = run_backtest(db_session, lookback=999)
    assert report.n_matches >= 1
    assert report.n_evaluated >= 1
    # 准确率应在 0-1
    assert 0.0 <= report.accuracy <= 1.0
    # Brier Score 应在合理区间
    assert 0.0 <= report.brier_score <= 2.0


def test_backtest_eng_cro_specific(db_session, seeded_eng_cro):
    """ENG vs CRO 2018 半决赛：实际客胜（英格兰视角 0-1 负）。"""
    # 跑预测
    eng = seeded_eng_cro["eng"]
    cro = seeded_eng_cro["cro"]
    hist = seeded_eng_cro["hist"]

    pred = _predict_for_backtest(eng, cro, hist)
    # 模型预测的客胜概率应该 > 0
    assert pred.away_win_prob > 0
    # Brier Score 贡献应在 0-2
    assert 0.0 <= pred.brier_contribution <= 2.0


def test_backtest_with_no_seed_data(db_session):
    """空数据库回测不崩，返回 0 评估."""
    report = run_backtest(db_session, lookback=999)
    assert report.n_matches == 0
    assert report.n_evaluated == 0
    assert report.accuracy == 0.0


def test_backtest_with_lookback_limit(db_session, seeded_eng_cro):
    """lookback 参数限制."""
    limited = run_backtest(db_session, lookback=0)
    assert limited.n_matches == 0
    assert limited.n_evaluated == 0

    unlimited = run_backtest(db_session, lookback=999)
    assert unlimited.n_matches >= 1


def test_backtest_handles_missing_teams(db_session):
    """球队不存在时跳过，不崩."""
    # 只插入 H2H 但不插 Team
    db_session.add(H2HHistoricalMatch(
        home_fifa_code="XXX", away_fifa_code="YYY",
        home_score=1, away_score=0,
        match_date=datetime(2018, 6, 15),
        competition="Test", stage="Test", neutral_venue=True,
    ))
    db_session.commit()

    report = run_backtest(db_session, lookback=999)
    assert report.n_matches == 1
    assert report.n_evaluated == 0
    assert report.n_skipped == 1
