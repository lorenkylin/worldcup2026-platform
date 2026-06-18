"""多源字段级仲裁协调器测试（v0.14.4）.

验证：
- preview_arbitration 只读不写库
- arbitrate_and_apply 按置信度写回字段
- manual 数据不被自动源覆盖
- 无数据时返回空摘要
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app import config as config_module
from app.models import Match
from app.services import multi_source_arbitration as msarb
from app.services.field_arbiter import FieldCandidate


class TestPreviewArbitration:
    def test_preview_does_not_modify_db(self, db_session):
        """preview 不应修改数据库."""
        match = db_session.query(Match).filter(Match.match_number == 1).first()
        original_status = match.status
        original_score = match.home_score

        wc26_games = [
            {
                "id": 1,
                "home_team_id": 1,
                "away_team_id": 2,
                "stadium_id": 1,
                "local_date": "2026-06-12 00:00",
                "finished": True,
                "time_elapsed": "FT",
                "home_score": 2,
                "away_score": 1,
                "type": "group",
                "group": "A",
                "matchday": 1,
            }
        ]

        with patch.object(config_module.settings, "api_football_enabled", False), \
             patch.object(config_module.settings, "api_football_key", ""), \
             patch.object(msarb, "_fetch_worldcup26_games", return_value=wc26_games), \
             patch.object(msarb, "_build_wc26_mappings", return_value=({1: "MEX", 2: "RSA"}, {1: "Estadio Azteca, Mexico City"})):
            result = msarb.preview_arbitration(db_session)

        assert result["previewed_matches"] >= 1
        db_session.refresh(match)
        assert match.status == original_status
        assert match.home_score == original_score

    def test_preview_no_data_returns_empty(self, db_session):
        with patch.object(config_module.settings, "api_football_enabled", False), \
             patch.object(config_module.settings, "api_football_key", ""), \
             patch.object(msarb, "_fetch_worldcup26_games", return_value=[]):
            result = msarb.preview_arbitration(db_session)
        assert result["previewed_matches"] == 0
        assert result["conflicts"] == 0
        assert result["matches"] == []


class TestArbitrateAndApply:
    def test_apply_updates_dynamic_fields(self, db_session):
        """动态字段（status/score）应在无 manual 保护时更新."""
        match = db_session.query(Match).filter(Match.match_number == 1).first()
        match.data_source = "worldcup26.ir"
        match.status = "live"
        db_session.commit()

        wc26_games = [
            {
                "id": 1,
                "home_team_id": 1,
                "away_team_id": 2,
                "stadium_id": 1,
                "local_date": "2026-06-12 00:00",
                "finished": True,
                "time_elapsed": "FT",
                "home_score": 2,
                "away_score": 1,
                "type": "group",
                "group": "A",
                "matchday": 1,
            }
        ]

        with patch.object(config_module.settings, "api_football_enabled", False), \
             patch.object(config_module.settings, "api_football_key", ""), \
             patch.object(msarb, "_fetch_worldcup26_games", return_value=wc26_games), \
             patch.object(msarb, "_build_wc26_mappings", return_value=({1: "MEX", 2: "RSA"}, {1: "Estadio Azteca, Mexico City"})):
            result = msarb.arbitrate_and_apply(db_session)

        assert result["arbitrated_matches"] >= 1
        db_session.refresh(match)
        assert match.status == "finished"
        assert match.home_score == 2
        assert match.away_score == 1

    def test_manual_source_not_overwritten(self, db_session):
        """manual 源的比赛不应被自动源覆盖."""
        match = db_session.query(Match).filter(Match.match_number == 1).first()
        match.data_source = "manual"
        match.status = "scheduled"
        original_score = match.home_score
        db_session.commit()

        wc26_games = [
            {
                "id": 1,
                "home_team_id": 1,
                "away_team_id": 2,
                "stadium_id": 1,
                "local_date": "2026-06-12 00:00",
                "finished": True,
                "time_elapsed": "FT",
                "home_score": 2,
                "away_score": 1,
                "type": "group",
                "group": "A",
                "matchday": 1,
            }
        ]

        with patch.object(config_module.settings, "api_football_enabled", False), \
             patch.object(config_module.settings, "api_football_key", ""), \
             patch.object(msarb, "_fetch_worldcup26_games", return_value=wc26_games), \
             patch.object(msarb, "_build_wc26_mappings", return_value=({1: "MEX", 2: "RSA"}, {1: "Estadio Azteca, Mexico City"})):
            result = msarb.arbitrate_and_apply(db_session)

        db_session.refresh(match)
        assert match.data_source == "manual"
        assert match.status == "scheduled"
        assert match.home_score == original_score
