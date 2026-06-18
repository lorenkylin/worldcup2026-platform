"""字段级置信度仲裁器测试（v0.14.4）.

验证：
- 同字段多候选值按置信度胜出
- 冲突检测与日志记录
- 状态机保护（scheduled → live → finished）
- manual 源永远胜出
- 业务校验（比分只在 live/finished 有效）
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.field_arbiter import (
    FIELD_CONFIDENCE,
    ARBITRABLE_FIELDS,
    FieldCandidate,
    arbitrate,
    get_confidence,
    log_conflicts,
    read_recent_conflicts,
)


class TestConfidenceConfig:
    def test_all_arbitrable_fields_have_confidence(self):
        """所有可仲裁字段都必须配置了置信度表."""
        assert set(FIELD_CONFIDENCE.keys()) == ARBITRABLE_FIELDS
        for field, sources in FIELD_CONFIDENCE.items():
            assert "manual" in sources, f"{field} 缺少 manual 源"
            assert sources["manual"] >= 100, f"{field} manual 源置信度必须最高"

    def test_get_confidence_unknown_field(self):
        assert get_confidence("unknown_field", "api-football") == 0

    def test_get_confidence_known_field(self):
        assert get_confidence("home_score", "api-football") == 95


class TestArbitrateBasic:
    def test_single_candidate_wins(self):
        cands = [
            FieldCandidate(field="home_score", value=2, source="api-football"),
        ]
        result = arbitrate(1, cands, current_status="live")
        assert result.match_number == 1
        assert result.decisions["home_score"].value == 2
        assert result.decisions["home_score"].source == "api-football"
        assert not result.conflicts

    def test_higher_confidence_wins(self):
        cands = [
            FieldCandidate(field="home_team_id", value=99, source="worldcup26.ir"),
            FieldCandidate(field="home_team_id", value=1, source="fixtures"),
        ]
        result = arbitrate(1, cands)
        decision = result.decisions["home_team_id"]
        assert decision.value == 1
        assert decision.source == "fixtures"
        assert decision.confidence == 100

    def test_manual_always_wins(self):
        cands = [
            FieldCandidate(field="home_score", value=2, source="api-football"),
            FieldCandidate(field="home_score", value=3, source="manual"),
        ]
        result = arbitrate(1, cands, current_status="live")
        decision = result.decisions["home_score"]
        assert decision.value == 3
        assert decision.source == "manual"
        assert "manual" in decision.reason

    def test_conflict_detected_when_values_differ(self):
        cands = [
            FieldCandidate(field="home_score", value=2, source="api-football"),
            FieldCandidate(field="home_score", value=1, source="worldcup26.ir"),
        ]
        result = arbitrate(1, cands, current_status="live")
        assert len(result.conflicts) == 1
        conflict = result.conflicts[0]
        assert conflict["field"] == "home_score"
        assert conflict["winner"]["source"] == "api-football"
        assert len(conflict["losers"]) == 1


class TestArbitrateStatusTransitions:
    def test_scheduled_to_live_allowed(self):
        cands = [FieldCandidate(field="status", value="live", source="api-football")]
        result = arbitrate(1, cands, current_status="scheduled")
        assert result.decisions["status"].value == "live"

    def test_finished_to_scheduled_blocked(self):
        cands = [FieldCandidate(field="status", value="scheduled", source="worldcup26.ir")]
        result = arbitrate(1, cands, current_status="finished")
        # 状态回退被拦截，该字段无有效决策
        assert "status" not in result.decisions

    def test_live_to_finished_allowed(self):
        cands = [FieldCandidate(field="status", value="finished", source="api-football")]
        result = arbitrate(1, cands, current_status="live")
        assert result.decisions["status"].value == "finished"


class TestArbitrateScoreValidation:
    def test_score_ignored_when_scheduled(self):
        cands = [FieldCandidate(field="home_score", value=2, source="api-football")]
        result = arbitrate(1, cands, current_status="scheduled")
        assert "home_score" not in result.decisions

    def test_score_allowed_when_live(self):
        cands = [FieldCandidate(field="home_score", value=2, source="api-football")]
        result = arbitrate(1, cands, current_status="live")
        assert result.decisions["home_score"].value == 2

    def test_score_allowed_when_finished(self):
        cands = [FieldCandidate(field="away_score", value=1, source="worldcup26.ir")]
        result = arbitrate(1, cands, current_status="finished")
        assert result.decisions["away_score"].value == 1


class TestConflictLogging:
    def test_log_and_read_conflicts(self, tmp_path):
        log_path = tmp_path / "conflicts.jsonl"
        conflicts = [
            {
                "match_number": 1,
                "field": "home_score",
                "winner": {"value": 2, "source": "api-football", "confidence": 95},
                "losers": [{"value": 1, "source": "worldcup26.ir", "confidence": 95}],
                "arbitrated_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        log_conflicts(conflicts, log_path=log_path)
        recent = read_recent_conflicts(limit=10, log_path=log_path)
        assert len(recent) == 1
        assert recent[0]["match_number"] == 1

    def test_read_recent_conflicts_limit(self, tmp_path):
        log_path = tmp_path / "conflicts.jsonl"
        for i in range(5):
            log_conflicts([{"match_number": i}], log_path=log_path)
        recent = read_recent_conflicts(limit=2, log_path=log_path)
        assert len(recent) == 2
        assert recent[-1]["match_number"] == 4

    def test_log_conflicts_empty_noop(self, tmp_path):
        log_path = tmp_path / "conflicts.jsonl"
        log_conflicts([], log_path=log_path)
        assert not log_path.exists()
