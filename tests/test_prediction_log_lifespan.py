"""v0.7.0b prediction_log lifespan 自动写库测试.

测试 auto_log_predictions() 核心契约:
  1. 3 模型 (v1_elo / v3_glicko2 / v7a_blend) 都能写库
  2. 1h dedup 正常
  3. 已完赛比赛跳过
  4. 窗口外比赛跳过
  5. 未知球队优雅降级
  6. 单条错误隔离不中断循环
  7. run_periodic_refresh 集成 step 3 正常返回
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

# Late binding fix: conftest 改写 app.db.SessionLocal,这里用 app_db.SessionLocal() 拿最新
from app import db as app_db
from app.models import Match, PredictionLog, Stadium, Team


# ============================================================
# Helpers
# ============================================================


def _add_future_match(
    db,
    match_id: int,
    home_code: str = "MEX",
    away_code: str = "RSA",
    home_elo: int = 1700,
    away_elo: int = 1500,
    days_from_now: int = 3,
    home_score=None,
    away_score=None,
    status: str = "scheduled",
):
    """添加未来/已完赛比赛. conftest 已 seed id=1 队 + 场."""
    # team ids 是 conftest 固定的
    if home_code == "MEX" and away_code == "RSA":
        home_id, away_id = 1, 2
    else:
        # 新球队
        from app.models import Team
        new_home = Team(
            id=100 + match_id,
            fifa_code=home_code,
            name_zh=home_code,
            name_en=home_code,
            group_name="X",
            flag_emoji="🏳",
            elo_rating=home_elo,
        )
        new_away = Team(
            id=200 + match_id,
            fifa_code=away_code,
            name_zh=away_code,
            name_en=away_code,
            group_name="X",
            flag_emoji="🏳",
            elo_rating=away_elo,
        )
        db.add_all([new_home, new_away])
        home_id, away_id = new_home.id, new_away.id
        db.commit()
    kickoff = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    m = Match(
        id=match_id,
        match_number=match_id,
        stage="小组赛",
        group_name="A",
        round_number=match_id,
        kickoff_at=kickoff,
        stadium_id=1,
        home_team_id=home_id,
        away_team_id=away_id,
        home_score=home_score,
        away_score=away_score,
        status=status,
        data_source="manual",
    )
    db.add(m)
    db.commit()
    return m


# ============================================================
# Tests
# ============================================================


def test_auto_log_predictions_basic_3_models():
    """1 场未来比赛 → 3 模型各写 1 条 = 3 条 PredictionLog."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        _add_future_match(db, match_id=100, days_from_now=2)
        result = auto_log_predictions(db)
        assert result["matches_scanned"] >= 1
        assert result["predictions_added"] == 3, (
            f"期望 3 条 (v1_elo + v3_glicko2 + v7a_blend), 实际 {result['predictions_added']}"
        )
        assert result["by_model"]["v1_elo"] == 1
        assert result["by_model"]["v3_glicko2"] == 1
        assert result["by_model"]["v7a_blend"] == 1
        assert result["predictions_skipped"] == 0
        assert len(result["errors"]) == 0
        # DB 验证
        logs = db.query(PredictionLog).filter(PredictionLog.match_id == 100).all()
        assert len(logs) == 3
        model_versions = {l.model_version for l in logs}
        assert model_versions == {"v1_elo", "v3_glicko2", "v7a_blend"}
    finally:
        db.close()


def test_auto_log_predictions_dedup_within_1h():
    """连续 2 次调用, 第 2 次全部 dedup 跳过."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        _add_future_match(db, match_id=101, days_from_now=2)
        r1 = auto_log_predictions(db)
        assert r1["predictions_added"] == 3
        # 立即再跑一次, 应该全部 dedup 跳过
        r2 = auto_log_predictions(db)
        assert r2["predictions_added"] == 0
        assert r2["predictions_skipped"] == 3
    finally:
        db.close()


def test_auto_log_predictions_skips_finished_match():
    """已完赛比赛 (有比分) 不在窗口内被写入."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        _add_future_match(
            db,
            match_id=102,
            days_from_now=1,
            home_score=2,
            away_score=1,
            status="finished",
        )
        result = auto_log_predictions(db)
        # 已完赛比赛 (有比分) 不在未完赛过滤内
        assert result["predictions_added"] == 0
        # 但 match 本身可能被 scan (filter 是 IS NULL OR IS NULL, 都不为 NULL 时跳过)
        logs = db.query(PredictionLog).filter(PredictionLog.match_id == 102).all()
        assert len(logs) == 0
    finally:
        db.close()


def test_auto_log_predictions_skips_outside_window():
    """窗口外比赛 (15 天后) 跳过."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        # lookahead=7 默认, 15 天后超出窗口
        _add_future_match(db, match_id=103, days_from_now=15)
        result = auto_log_predictions(db, lookahead_days=7)
        # MEX-RSA id=1 旧 match 在 6/11, 也超出窗口 (now=测试运行时, 6/11 远在过去)
        # 所以 scanned=0
        assert result["predictions_added"] == 0
    finally:
        db.close()


def test_auto_log_predictions_missing_team_graceful():
    """未知球队 (不在 hicruben/glicko2) 优雅降级, 不中断其他写入."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        # XXX 队不在 elo 数据中
        _add_future_match(
            db, match_id=104, home_code="XXX", away_code="YYY", days_from_now=2
        )
        result = auto_log_predictions(db)
        # 3 个 model 都返回 None (缺数据), 不写库, 不报 error
        assert result["predictions_added"] == 0
        # errors 应为空 (predict_fn 返回 None 不是异常)
        assert len(result["errors"]) == 0
    finally:
        db.close()


def test_auto_log_predictions_subset_models():
    """只写 v1_elo + v7a_blend, 不写 v3_glicko2."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        _add_future_match(db, match_id=105, days_from_now=2)
        result = auto_log_predictions(db, models=("v1_elo", "v7a_blend"))
        assert result["predictions_added"] == 2
        assert result["by_model"]["v1_elo"] == 1
        assert result["by_model"]["v7a_blend"] == 1
        assert "v3_glicko2" not in result["by_model"]
    finally:
        db.close()


def test_run_periodic_refresh_includes_predictions_step(monkeypatch):
    """run_periodic_refresh 应包含 predictions_added / by_model 字段 (v0.7.0b step 3)."""
    from app.services import periodic_refresh
    from app.services.periodic_refresh import run_periodic_refresh

    # 隔离外部多源同步：测试只关心 predictions 步骤被正确编排
    monkeypatch.setattr(
        "app.services.multi_source_sync.full_sync",
        lambda _db: {"ok": True, "primary_source": "test"},
    )

    db = app_db.SessionLocal()
    try:
        _add_future_match(db, match_id=106, days_from_now=2)
        result = run_periodic_refresh(db, fb_client=None)
        # Step 1: odds snapshot
        assert "snapshots_added" in result
        # Step 2: fb-data (skipped 因 api_key 未配置)
        assert result.get("fb_status") == "skipped"
        # Step 3 (v0.7.0b): predictions
        assert "predictions_added" in result
        assert result["predictions_added"] == 3
        assert "predictions_by_model" in result
        assert result["predictions_by_model"]["v1_elo"] == 1
    finally:
        db.close()


def test_auto_log_predictions_probabilities_valid():
    """3 模型预测概率都满足: home + draw + away = 1.0, 范围 [0, 1]."""
    from app.services.prediction_log import auto_log_predictions

    db = app_db.SessionLocal()
    try:
        _add_future_match(db, match_id=107, days_from_now=2)
        auto_log_predictions(db)
        logs = db.query(PredictionLog).filter(PredictionLog.match_id == 107).all()
        for log in logs:
            p_sum = log.pred_home_win + log.pred_draw + log.pred_away_win
            assert 0.99 <= p_sum <= 1.01, (
                f"{log.model_version}: probs sum={p_sum} 不接近 1.0"
            )
            for field in ("pred_home_win", "pred_draw", "pred_away_win"):
                p = getattr(log, field)
                assert 0.0 <= p <= 1.0, f"{log.model_version}.{field}={p} 越界"
    finally:
        db.close()


class TestSnapshotGroup:
    """snapshot_group 自动分组逻辑."""

    def test_compute_snapshot_group_time_windows(self):
        """各时间窗口边界计算正确."""
        from app.services.prediction_log import _compute_snapshot_group

        kickoff = datetime(2026, 7, 4, 20, 0, tzinfo=timezone.utc)
        cases = [
            # 赛前
            (kickoff - timedelta(days=10), "pre_7d"),
            (kickoff - timedelta(days=7, seconds=1), "pre_7d"),
            (kickoff - timedelta(days=7), "pre_3d"),
            (kickoff - timedelta(days=4), "pre_3d"),
            (kickoff - timedelta(days=3, seconds=1), "pre_3d"),
            (kickoff - timedelta(days=3), "pre_1d"),
            (kickoff - timedelta(days=2), "pre_1d"),
            (kickoff - timedelta(days=1, seconds=1), "pre_1d"),
            (kickoff - timedelta(days=1), "pre_1h"),
            (kickoff - timedelta(hours=12), "pre_1h"),
            (kickoff - timedelta(seconds=1), "pre_1h"),
            (kickoff, "pre_1h"),
            # 赛中
            (kickoff + timedelta(seconds=1), "live"),
            (kickoff + timedelta(hours=2, minutes=59), "live"),
            # 赛后
            (kickoff + timedelta(hours=3), "post"),
            (kickoff + timedelta(days=1), "post"),
        ]
        for predicted_at, expected in cases:
            assert _compute_snapshot_group(predicted_at, kickoff) == expected, (
                f"predicted_at={predicted_at}, expected={expected}"
            )

    def test_compute_snapshot_group_missing_time(self):
        """缺失 predicted_at 或 kickoff_at 时返回 None."""
        from app.services.prediction_log import _compute_snapshot_group

        now = datetime.now(timezone.utc)
        assert _compute_snapshot_group(None, now) is None
        assert _compute_snapshot_group(now, None) is None
        assert _compute_snapshot_group(None, None) is None

    def test_compute_snapshot_group_naive_datetime(self):
        """naive UTC 与 aware UTC 可混用."""
        from app.services.prediction_log import _compute_snapshot_group

        kickoff = datetime(2026, 7, 4, 20, 0)  # naive UTC
        predicted = datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc)  # aware UTC
        # 正好 3 天 -> pre_1d
        assert _compute_snapshot_group(predicted, kickoff) == "pre_1d"
        predicted2 = datetime(2026, 7, 1, 19, 59, 59, tzinfo=timezone.utc)
        assert _compute_snapshot_group(predicted2, kickoff) == "pre_3d"

    def test_auto_log_predictions_sets_snapshot_group(self):
        """auto_log_predictions 写入时会自动设置 snapshot_group."""
        from app.services.prediction_log import auto_log_predictions

        db = app_db.SessionLocal()
        try:
            _add_future_match(db, match_id=200, days_from_now=2)
            result = auto_log_predictions(db)
            assert result["predictions_added"] == 3
            logs = db.query(PredictionLog).filter(PredictionLog.match_id == 200).all()
            assert len(logs) == 3
            for log in logs:
                # 2 天后属于 pre_1d 窗口
                assert log.snapshot_group == "pre_1d"
        finally:
            db.close()
