"""v0.11 Forward-Testing 单元测试.

测试 compute_live_accuracy / compute_live_window_accuracy 服务.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models import Match, Team, PredictionLog
from app.services.prediction_log import (
    record_prediction,
    compute_live_accuracy,
    compute_live_window_accuracy,
)


# === Fixtures (Match 用 ID-based 外键) ===

@pytest.fixture
def team_a(db_session):
    t = Team(fifa_code="AAA", name_zh="测试A", name_en="TestA", group_name="A")
    db_session.add(t); db_session.commit(); db_session.refresh(t)
    return t


@pytest.fixture
def team_b(db_session):
    t = Team(fifa_code="BBB", name_zh="测试B", name_en="TestB", group_name="A")
    db_session.add(t); db_session.commit(); db_session.refresh(t)
    return t


def _make_match(db_session, team_a, team_b, kickoff_at, home_score=None, away_score=None, status="scheduled", match_number=99001):
    m = Match(
        match_number=match_number,
        stage="小组赛",
        kickoff_at=kickoff_at,
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        home_score=home_score,
        away_score=away_score,
        status=status,
    )
    db_session.add(m); db_session.commit(); db_session.refresh(m)
    return m


@pytest.fixture
def finished_match(db_session, team_a, team_b):
    """已完赛比赛 - 1:0 主胜."""
    return _make_match(
        db_session, team_a, team_b,
        kickoff_at=datetime.now(timezone.utc) - timedelta(hours=2),
        home_score=1, away_score=0, status="finished", match_number=99001,
    )


@pytest.fixture
def pending_match(db_session, team_a, team_b):
    """未完赛比赛 - 未来 1 天."""
    return _make_match(
        db_session, team_a, team_b,
        kickoff_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="scheduled", match_number=99002,
    )


# === compute_live_accuracy 测试 ===

def test_live_accuracy_no_data(db_session):
    """无数据: 返回 no_data + 提示."""
    result = compute_live_accuracy(db_session)
    assert result["is_live_filter"] is None
    assert result["by_model"] == {}
    assert result["overall"]["samples"] == 0
    assert result["overall"]["accuracy"] is None
    assert result["data_status"] == "no_data"
    assert "无真 forward 数据" in result["note"]


def test_live_accuracy_live_only(db_session, finished_match):
    """只有 live 预测: data_status=live_only."""
    log = record_prediction(
        db_session,
        match_id=finished_match.id,
        model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2,
        is_live=True,
    )
    log.actual_outcome = "home"
    log.actual_home_score = 1
    log.actual_away_score = 0
    log.correct = 1
    log.brier_score = 0.32
    log.log_loss = 0.51
    db_session.commit()

    result = compute_live_accuracy(db_session, is_live=True)
    assert result["data_status"] == "live_only"
    assert result["overall"]["samples"] == 1
    assert result["overall"]["accuracy"] == 1.0
    assert result["overall"]["brier"] == 0.32
    assert "v3_glicko2" in result["by_model"]


def test_live_accuracy_backfill_only(db_session, finished_match):
    """只有 backfill 预测: data_status=backfill_only."""
    log = record_prediction(
        db_session,
        match_id=finished_match.id,
        model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2,
        is_live=False,
    )
    log.actual_outcome = "home"
    log.correct = 1
    db_session.commit()

    result = compute_live_accuracy(db_session, is_live=False)
    assert result["data_status"] == "backfill_only"
    assert result["overall"]["samples"] == 1


def test_live_accuracy_mixed(db_session, finished_match):
    """live + backfill: data_status=mixed."""
    log1 = record_prediction(
        db_session, match_id=finished_match.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2, is_live=True,
    )
    log1.actual_outcome = "home"; log1.correct = 1; db_session.commit()

    # 强制第二条 backfill 跳过 1h dedup (用较早 predicted_at)
    log2 = record_prediction(
        db_session, match_id=finished_match.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2, is_live=False,
    )
    # 第二条被 dedup 跳过 (1h 内同 match+model), 用直接插入
    if log2 is None:
        from datetime import datetime, timezone, timedelta
        log2 = PredictionLog(
            match_id=finished_match.id, model_version="v3_glicko2",
            predicted_at=datetime.now(timezone.utc) - timedelta(hours=2),
            pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2,
            predicted_outcome="H", is_live=False,
        )
        db_session.add(log2)
    log2.actual_outcome = "home"; log2.correct = 0; db_session.commit()

    result = compute_live_accuracy(db_session)
    assert result["data_status"] == "mixed"
    assert result["overall"]["samples"] == 2
    assert result["overall"]["accuracy"] == 0.5

    result_live = compute_live_accuracy(db_session, is_live=True)
    assert result_live["overall"]["accuracy"] == 1.0

    result_bf = compute_live_accuracy(db_session, is_live=False)
    assert result_bf["overall"]["accuracy"] == 0.0


def test_live_accuracy_by_model_filter(db_session, finished_match):
    """model_version 参数过滤."""
    log1 = record_prediction(
        db_session, match_id=finished_match.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2, is_live=True,
    )
    log1.actual_outcome = "home"; log1.correct = 1; db_session.commit()

    log2 = record_prediction(
        db_session, match_id=finished_match.id, model_version="v1_elo",
        pred_home_win=0.5, pred_draw=0.3, pred_away_win=0.2, is_live=True,
    )
    log2.actual_outcome = "home"; log2.correct = 1; db_session.commit()

    result = compute_live_accuracy(db_session, is_live=True, model_version="v3_glicko2")
    assert "v3_glicko2" in result["by_model"]
    assert "v1_elo" not in result["by_model"]


def test_live_accuracy_unsettled_excluded(db_session, finished_match):
    """未结算 (correct IS NULL) 不计入."""
    record_prediction(
        db_session, match_id=finished_match.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2, is_live=True,
    )
    # 不写 correct, 留空
    db_session.commit()

    result = compute_live_accuracy(db_session, is_live=True)
    assert result["overall"]["samples"] == 0


# === compute_live_window_accuracy 测试 ===

def test_live_window_no_data(db_session):
    """近 N 天无 live forward."""
    result = compute_live_window_accuracy(db_session, days=7)
    assert result["days"] == 7
    assert result["by_model"] == {}
    assert result["overall"]["samples"] == 0
    assert "无 live forward 数据" in result["note"]


def test_live_window_filters_backfill(db_session, finished_match):
    """live_window 只看 live, 排除 backfill."""
    log1 = record_prediction(
        db_session, match_id=finished_match.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2, is_live=True,
    )
    log1.actual_outcome = "home"; log1.correct = 1; db_session.commit()

    # 直接插 backfill 行 (绕开 1h dedup)
    from datetime import datetime, timezone, timedelta
    log2 = PredictionLog(
        match_id=finished_match.id, model_version="v3_glicko2",
        predicted_at=datetime.now(timezone.utc) - timedelta(hours=2),
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2,
        predicted_outcome="H", is_live=False,
    )
    log2.actual_outcome = "home"; log2.correct = 0
    db_session.add(log2); db_session.commit()

    result = compute_live_window_accuracy(db_session, days=7)
    assert result["overall"]["samples"] == 1
    assert result["overall"]["accuracy"] == 1.0


def test_live_window_excludes_old(db_session, team_a, team_b):
    """预测超过 N 天不计入."""
    m_old = _make_match(
        db_session, team_a, team_b,
        kickoff_at=datetime.now(timezone.utc) - timedelta(days=10),
        home_score=1, away_score=0, status="finished", match_number=99010,
    )
    log_old = record_prediction(
        db_session, match_id=m_old.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2, is_live=True,
    )
    log_old.actual_outcome = "home"; log_old.correct = 1
    log_old.predicted_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    result = compute_live_window_accuracy(db_session, days=7)
    assert result["overall"]["samples"] == 0


# === record_prediction 字段测试 ===

def test_record_prediction_default_is_live_false(db_session, pending_match):
    """record_prediction 默认 is_live=False (兼容旧调用方)."""
    log = record_prediction(
        db_session, match_id=pending_match.id, model_version="v3_glicko2",
        pred_home_win=0.5, pred_draw=0.3, pred_away_win=0.2,
    )
    assert log is not None
    assert log.is_live is False


def test_record_prediction_is_live_true(db_session, pending_match):
    """record_prediction 显式 is_live=True."""
    log = record_prediction(
        db_session, match_id=pending_match.id, model_version="v3_glicko2",
        pred_home_win=0.5, pred_draw=0.3, pred_away_win=0.2,
        is_live=True,
    )
    assert log is not None
    assert log.is_live is True


def test_record_prediction_snapshot_group(db_session, pending_match):
    """record_prediction snapshot_group 字段."""
    log = record_prediction(
        db_session, match_id=pending_match.id, model_version="v3_glicko2",
        pred_home_win=0.5, pred_draw=0.3, pred_away_win=0.2,
        is_live=True,
        snapshot_group="pre_7d_AAA_BBB",
    )
    assert log is not None
    assert log.snapshot_group == "pre_7d_AAA_BBB"


def test_record_prediction_dedup_works_with_is_live(db_session, pending_match):
    """1h dedup 对 live 也生效."""
    log1 = record_prediction(
        db_session, match_id=pending_match.id, model_version="v3_glicko2",
        pred_home_win=0.5, pred_draw=0.3, pred_away_win=0.2,
        is_live=True,
    )
    log2 = record_prediction(
        db_session, match_id=pending_match.id, model_version="v3_glicko2",
        pred_home_win=0.6, pred_draw=0.2, pred_away_win=0.2,
        is_live=True,
    )
    assert log1 is not None
    assert log2 is None
