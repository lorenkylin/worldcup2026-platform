"""prediction_log 服务单测 (v0.6.0+)."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from app.db import Base
from app.models import Team, Stadium, Match, PredictionLog
from app.services.prediction_log import (
    _score_to_outcome, _outcome_to_letter,
    _compute_brier, _compute_log_loss,
    record_prediction, settle_pending_predictions,
    compute_accuracy_stats, get_top_prediction_bias,
)


@pytest.fixture
def db_session():
    """内存 SQLite + 必要 seed."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    # Seed: 2 teams + 1 stadium
    t1 = Team(fifa_code="MEX", name_zh="墨西哥", name_en="Mexico", group_name="A", elo_rating=1834)
    t2 = Team(fifa_code="RSA", name_zh="南非", name_en="South Africa", group_name="A", elo_rating=1591)
    s = Stadium(name_zh="球场1", name_en="Stadium 1", city="Mexico City", country="Mexico")
    db.add_all([t1, t2, s])
    db.commit()
    m = Match(match_number=1, stage="小组赛", group_name="A", round_number=1,
              kickoff_at=datetime(2026, 6, 11, 13, 0), stadium_id=1,
              home_team_id=1, away_team_id=2, status="finished", home_score=2, away_score=0)
    db.add(m)
    db.commit()
    yield db
    db.close()


class TestHelpers:
    def test_score_to_outcome(self):
        assert _score_to_outcome(2, 0) == "home"
        assert _score_to_outcome(0, 2) == "away"
        assert _score_to_outcome(1, 1) == "draw"

    def test_outcome_to_letter(self):
        assert _outcome_to_letter("home") == "H"
        assert _outcome_to_letter("draw") == "D"
        assert _outcome_to_letter("away") == "A"

    def test_brier_perfect(self):
        """完美预测 Brier = 0."""
        b = _compute_brier(1.0, 0.0, 0.0, "home")
        assert abs(b) < 1e-10

    def test_brier_worst(self):
        """最差预测 Brier = 2."""
        b = _compute_brier(0.0, 0.0, 1.0, "home")
        assert abs(b - 2.0) < 1e-10

    def test_log_loss_decreases_with_confidence(self):
        l1 = _compute_log_loss(0.9, 0.05, 0.05, "home")
        l2 = _compute_log_loss(0.5, 0.3, 0.2, "home")
        assert l1 < l2


class TestRecordPrediction:
    def test_records_first_time(self, db_session):
        log = record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.7, pred_draw=0.2, pred_away_win=0.1,
            elo_home=1834, elo_away=1591,
        )
        assert log is not None
        assert log.id is not None
        assert log.predicted_outcome == "H"

    def test_dedup_within_1_hour(self, db_session):
        log1 = record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.7, pred_draw=0.2, pred_away_win=0.1,
        )
        log2 = record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.6, pred_draw=0.3, pred_away_win=0.1,
        )
        # 第二次应在 1h 内被 dedup
        assert log1 is not None
        assert log2 is None

    def test_different_model_no_dedup(self, db_session):
        log1 = record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.7, pred_draw=0.2, pred_away_win=0.1,
        )
        log2 = record_prediction(
            db_session, match_id=1, model_version="v3_glicko2",
            pred_home_win=0.6, pred_draw=0.3, pred_away_win=0.1,
        )
        assert log1 is not None
        assert log2 is not None  # 不同 model 可同时存在


class TestSettle:
    def test_settle_winning_prediction(self, db_session):
        record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.7, pred_draw=0.2, pred_away_win=0.1,
        )
        count = settle_pending_predictions(db_session)
        assert count == 1
        log = db_session.query(PredictionLog).first()
        assert log.actual_outcome == "home"
        assert log.correct == 1  # H 预测正确
        assert log.brier_score is not None
        assert log.log_loss is not None

    def test_settle_losing_prediction(self, db_session):
        record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.1, pred_draw=0.2, pred_away_win=0.7,  # 预测客胜
        )
        # 但实际主胜 2-0
        settle_pending_predictions(db_session)
        log = db_session.query(PredictionLog).first()
        assert log.correct == 0  # A 预测错

    def test_settle_idempotent(self, db_session):
        record_prediction(
            db_session, match_id=1, model_version="v1_elo",
            pred_home_win=0.7, pred_draw=0.2, pred_away_win=0.1,
        )
        c1 = settle_pending_predictions(db_session)
        c2 = settle_pending_predictions(db_session)
        assert c1 == 1
        assert c2 == 0  # 第二次没有未结算的


class TestAccuracyStats:
    def test_no_data_returns_null(self, db_session):
        stats = compute_accuracy_stats(db_session)
        assert stats["n_settled"] == 0
        assert stats["accuracy"] is None

    def test_settled_stats(self, db_session):
        # 3 个预测, 2 正确 (MEX 主胜 2-0)
        for i, (ph, pd_, pa) in enumerate([
            (0.7, 0.2, 0.1),  # 正确 H
            (0.3, 0.3, 0.4),  # 错误 A
            (0.5, 0.3, 0.2),  # 正确 H
        ]):
            record_prediction(
                db_session, match_id=1, model_version=f"m{i}",
                pred_home_win=ph, pred_draw=pd_, pred_away_win=pa,
            )
        settle_pending_predictions(db_session)
        stats = compute_accuracy_stats(db_session)
        assert stats["n_settled"] == 3
        assert stats["accuracy"] == round(2/3, 4)
        assert stats["brier"] is not None
        assert stats["log_loss"] is not None
        assert "v1_elo" not in stats["by_model"]  # 模型名是 m0/m1/m2

    def test_by_model_breakdown(self, db_session):
        record_prediction(db_session, match_id=1, model_version="v1_elo",
                          pred_home_win=0.7, pred_draw=0.2, pred_away_win=0.1)
        record_prediction(db_session, match_id=1, model_version="v3_glicko2",
                          pred_home_win=0.6, pred_draw=0.3, pred_away_win=0.1)
        settle_pending_predictions(db_session)
        stats = compute_accuracy_stats(db_session)
        assert "v1_elo" in stats["by_model"]
        assert "v3_glicko2" in stats["by_model"]


class TestTopBias:
    def test_top_bias_finds_wrong_predictions(self, db_session):
        # 高 confidence 预测客胜, 但实际主胜 2-0 → 偏差
        record_prediction(db_session, match_id=1, model_version="v3_glicko2",
                          pred_home_win=0.05, pred_draw=0.05, pred_away_win=0.90)
        settle_pending_predictions(db_session)
        bias = get_top_prediction_bias(db_session, model_version="v3_glicko2", n=5)
        assert len(bias) == 1
        assert bias[0]["match_id"] == 1
        # surprise = 0.90 (预测 confidence) - 0.05 (实际 H 的概率) = 0.85
        assert bias[0]["surprise_score"] > 0.8
