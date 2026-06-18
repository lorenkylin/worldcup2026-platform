"""Cockpit 总览驾驶舱 API 测试（v0.14.2）."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Match, Team


@pytest.fixture
def client():
    return TestClient(app)


def _add_future_match(db, match_id: int, home_id: int, away_id: int, days: int = 1):
    m = Match(
        id=match_id,
        match_number=match_id,
        stage="小组赛",
        group_name="A",
        round_number=1,
        kickoff_at=datetime.now(timezone.utc) + timedelta(days=days),
        stadium_id=1,
        home_team_id=home_id,
        away_team_id=away_id,
        status="scheduled",
        data_source="worldcup26.ir",
    )
    db.add(m)
    db.commit()


class TestCockpitSummary:
    def test_summary_endpoint_returns_key_sections(self, client: TestClient):
        """ Cockpit summary 端点返回所有关键板块."""
        response = client.get("/api/cockpit/summary")
        assert response.status_code == 200
        data = response.json()
        assert "generated_at" in data
        assert "tournament_progress" in data
        assert "qualification_summary" in data
        assert "data_health" in data
        assert "critical_matches" in data
        assert "model_consensus" in data
        assert "elo_top_teams" in data

    def test_tournament_progress_counts(self, client: TestClient, db_session):
        """进度统计与 DB 比赛数一致."""
        total = db_session.query(Match).count()
        response = client.get("/api/cockpit/summary")
        progress = response.json()["tournament_progress"]
        assert progress["total_matches"] == total
        assert "milestones" in progress
        assert progress["milestones"]["r32_locked"] in (True, False)

    def test_critical_matches_within_72h(self, client: TestClient, db_session):
        """未来比赛出现在 critical_matches 中."""
        home = Team(id=101, fifa_code="ARG", name_zh="阿根廷", name_en="Argentina", group_name="A", flag_emoji="🇦🇷", elo_rating=1900)
        away = Team(id=102, fifa_code="BRA", name_zh="巴西", name_en="Brazil", group_name="A", flag_emoji="🇧🇷", elo_rating=1850)
        db_session.add_all([home, away])
        db_session.commit()
        _add_future_match(db_session, 200, 101, 102, days=1)

        response = client.get("/api/cockpit/summary")
        data = response.json()
        ids = [m["match_id"] for m in data["critical_matches"]]
        assert 200 in ids
        match = next(m for m in data["critical_matches"] if m["match_id"] == 200)
        assert match["impact_label"] in ("头名之争", "强弱对话", "生死战", "出线关键战", "荣誉战")
        assert "consensus" in match["prediction"]

    def test_elo_top_teams(self, client: TestClient):
        """Elo Top 5 按评分降序."""
        response = client.get("/api/cockpit/summary")
        tops = response.json()["elo_top_teams"]
        assert len(tops) <= 5
        if len(tops) >= 2:
            assert tops[0]["elo_rating"] >= tops[1]["elo_rating"]

    def test_qualification_summary_counts(self, client: TestClient):
        """晋级摘要字段完整."""
        response = client.get("/api/cockpit/summary")
        summary = response.json()["qualification_summary"]
        for key in ("qualified", "eliminated", "pending", "direct_qualifiers", "third_place_qualifiers", "best_thirds"):
            assert key in summary
        assert summary["qualified"] + summary["eliminated"] + summary["pending"] == 48 or summary["qualified"] == 0
