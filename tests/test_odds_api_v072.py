"""v0.7.2 赔率 API + 模型对比单元/集成测试."""
from datetime import datetime, timezone

import pytest

from app.models import Match, MatchOdds
from app.services.odds_api_client import (
    fetch_upcoming_odds,
    upsert_to_match_odds,
    service_status,
    _elo_to_decimal_odds,
)
from app.services.model_odds_compare import (
    compare_match_odds,
    find_value_bets,
    _value_tier,
)


@pytest.fixture
def minimal_match(db_session):
    """确保 match_id=1 是 scheduled 状态 + 未来日期."""
    m = db_session.query(Match).filter(Match.id == 1).first()
    if m is None:
        pytest.skip("conftest 未 seed match_id=1")
    m.status = "scheduled"
    m.kickoff_at = datetime(2099, 6, 11, 19, 0, tzinfo=timezone.utc)
    m.home_score = None
    m.away_score = None
    db_session.commit()
    return m


# === _elo_to_decimal_odds ===
def test_elo_to_decimal_odds_higher_elo_lower_home_odds():
    """主队 Elo 高 200,主胜赔率应小于客胜赔率."""
    home_wins = _elo_to_decimal_odds(1800, 1600)
    home_loses = _elo_to_decimal_odds(1600, 1800)
    assert home_wins["home_win"] < home_loses["home_win"]
    assert home_wins["away_win"] > home_loses["away_win"]


def test_elo_to_decimal_odds_equal_teams_away_acceptable():
    """Elo 相等时(1500 vs 1500,主队+50)主队略占优,主胜赔率最低."""
    odds = _elo_to_decimal_odds(1500, 1500)
    # home_elo=1550(含主队加分),away=1500 → 主队略占优
    # 主胜概率 ~0.55, 平局 ~0.28, 客胜 ~0.17
    assert odds["home_win"] < odds["draw"]
    assert odds["away_win"] > odds["draw"]


def test_elo_to_decimal_odds_min_prob_floor():
    """极强主队(1900 vs 1000)主胜概率不会贴 0.95 上限."""
    odds = _elo_to_decimal_odds(1900, 1000)
    # 1.0/0.95 ≈ 1.0526,实际四舍五入到 2 位可能是 1.05
    assert odds["home_win"] >= 1.0 / 0.96  # 容差 floor
    assert odds["home_win"] <= 1.0 / 0.02   # 主胜概率 ≥ 0.02


# === _value_tier ===
def test_value_tier_thresholds():
    """value 率档位划分与阈值一致."""
    assert _value_tier(0.03, 0.05) == "none"
    assert _value_tier(0.06, 0.05) == "edge"
    assert _value_tier(0.09, 0.05) == "edge"
    assert _value_tier(0.11, 0.05) == "strong"
    assert _value_tier(0.30, 0.05) == "strong"


# === upsert_to_match_odds ===
def test_upsert_to_match_odds_inserts_new_row(db_session, minimal_match):
    """新 (match_id, bookmaker) → INSERT."""
    payload = [{
        "match_id": 1,
        "bookmaker": "test_bookmaker",
        "home_win": 2.10,
        "draw": 3.40,
        "away_win": 3.60,
        "over_2_5": 1.95,
        "under_2_5": 2.05,
        "source": "test",
        "fetched_at": datetime.now(timezone.utc),
    }]
    written = upsert_to_match_odds(db_session, payload)
    assert written == 1

    row = db_session.query(MatchOdds).filter(MatchOdds.match_id == 1).first()
    assert row is not None
    assert row.home_win == 2.10
    assert row.source == "test"


def test_upsert_to_match_odds_updates_existing_row(db_session, minimal_match):
    """同 (match_id, bookmaker) → UPDATE,不增加行."""
    payload_base = {
        "match_id": 1,
        "bookmaker": "betpawa",
        "home_win": 2.10,
        "draw": 3.40,
        "away_win": 3.60,
        "source": "test",
    }
    upsert_to_match_odds(db_session, [payload_base])

    payload_updated = {**payload_base, "home_win": 2.50}
    upsert_to_match_odds(db_session, [payload_updated])

    rows = db_session.query(MatchOdds).filter(MatchOdds.match_id == 1).all()
    assert len(rows) == 1
    assert rows[0].home_win == 2.50


def test_upsert_to_match_odds_skips_missing_required_keys(db_session, minimal_match):
    """缺 match_id/bookmaker → 跳过."""
    payload = [{"home_win": 2.10, "draw": 3.40, "away_win": 3.60}]
    written = upsert_to_match_odds(db_session, payload)
    assert written == 0


# === service_status ===
def test_service_status_returns_dict():
    """service_status 返回完整字典."""
    status = service_status()
    assert "enabled" in status
    assert "provider" in status
    assert "has_api_key" in status
    assert "rate_limit_per_min" in status
    assert "cache_ttl_seconds" in status


# === fetch_upcoming_odds (mock) ===
def test_fetch_upcoming_odds_returns_dicts(db_session, minimal_match):
    """mock 模式下返回 List[Dict]."""
    target_date = minimal_match.kickoff_at.date().isoformat()
    result = fetch_upcoming_odds(db_session, target_dates=[target_date])
    assert isinstance(result, list)
    assert len(result) >= 1
    item = result[0]
    assert "match_id" in item
    assert "bookmaker" in item
    assert "home_win" in item
    assert "source" in item


# === compare_match_odds ===
def test_compare_match_odds_returns_expected_structure(db_session, minimal_match):
    """模型 vs 赔率对比返回完整结构."""
    fetch_date = minimal_match.kickoff_at.date().isoformat()
    payload = fetch_upcoming_odds(db_session, target_dates=[fetch_date])
    upsert_to_match_odds(db_session, payload)

    result = compare_match_odds(db_session, match_id=1, model="blend")
    if result is None:
        pytest.skip("blend 模型无 MEX/RSA 评分,跳过")
    assert result["model"] == "blend"
    assert "model_probs" in result
    assert "market_probs" in result
    assert "value_bet" in result


def test_compare_match_odds_invalid_model(db_session, minimal_match):
    """model=invalid 应被 endpoint 校验(此处直接测服务函数不抛)."""
    fetch_date = minimal_match.kickoff_at.date().isoformat()
    payload = fetch_upcoming_odds(db_session, target_dates=[fetch_date])
    upsert_to_match_odds(db_session, payload)

    result = compare_match_odds(db_session, match_id=1, model="invalid_model")
    assert result is None


# === find_value_bets ===
def test_find_value_bets_returns_list(db_session, minimal_match):
    """find_value_bets 返回列表(可能为空)."""
    fetch_date = minimal_match.kickoff_at.date().isoformat()
    payload = fetch_upcoming_odds(db_session, target_dates=[fetch_date])
    upsert_to_match_odds(db_session, payload)

    result = find_value_bets(db_session, model="blend", min_tier="edge", limit=5)
    assert isinstance(result, list)
    assert len(result) <= 5
    for item in result:
        assert "match_id" in item
        assert "best_outcome" in item
        assert "best_rate" in item
        assert "tier" in item
        assert item["tier"] in ("edge", "strong")