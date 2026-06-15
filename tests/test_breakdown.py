"""F2 可解释性面板 - factors_breakdown 字段测试."""

import pytest

from app.services.prediction import predict_match, _factors_breakdown
from app.models import Team


# =============== 单元测试 ===============
def test_factors_breakdown_returns_all_sections():
    """factors_breakdown 必须包含 elo / form / h2h / lambda 四块."""
    home = Team(
        id=1, fifa_code="ENG", name_zh="英格兰", name_en="England",
        group_name="K", elo_rating=1700, fifa_rank=5,
        recent_form_points=10, recent_goal_diff=3,
    )
    away = Team(
        id=2, fifa_code="CRO", name_zh="克罗地亚", name_en="Croatia",
        group_name="K", elo_rating=1680, fifa_rank=10,
        recent_form_points=7, recent_goal_diff=1,
    )
    h2h = {"home_wins": 0, "away_wins": 1, "draws": 0, "sample": 1, "source": "history"}
    from app.services.prediction import _elo_to_lambda, _apply_recent_form
    home_lambda, away_lambda = _elo_to_lambda(home.elo_rating, away.elo_rating)
    home_lambda, away_lambda = _apply_recent_form(
        home_lambda, away_lambda, home.recent_form_points, away.recent_form_points
    )

    factors = _factors_breakdown(
        home, away, home_lambda, away_lambda,
        home.recent_form_points, away.recent_form_points, h2h
    )

    # 验证四个 section 都存在
    assert "elo" in factors
    assert "form" in factors
    assert "h2h" in factors
    assert "lambda" in factors

    # Elo
    elo = factors["elo"]
    assert elo["home_elo"] == 1700
    assert elo["away_elo"] == 1680
    assert elo["diff"] == 20
    assert elo["home_advantage"] == 60  # HOME_ADVANTAGE
    assert "contribution_to_lambda" in elo

    # Form
    form = factors["form"]
    assert form["home_points"] == 10
    assert form["away_points"] == 7
    assert form["diff"] == 3
    assert form["applied"] is True
    assert form["weight"] == 0.10

    # H2H
    h2h_out = factors["h2h"]
    assert h2h_out["sample"] == 1
    assert h2h_out["home_wins"] == 0
    assert h2h_out["away_wins"] == 1
    assert h2h_out["draws"] == 0
    assert h2h_out["source"] == "history"

    # Lambda
    lam = factors["lambda"]
    assert lam["home"] > 0
    assert lam["away"] > 0
    assert lam["base"] == 1.35


def test_factors_breakdown_with_no_form_data():
    """无 form 数据时 form.applied = False，diff = None."""
    home = Team(
        id=1, fifa_code="AAA", name_zh="A", name_en="A",
        group_name="A", elo_rating=1500, recent_form_points=None,
    )
    away = Team(
        id=2, fifa_code="BBB", name_zh="B", name_en="B",
        group_name="A", elo_rating=1500, recent_form_points=None,
    )
    from app.services.prediction import _elo_to_lambda
    home_lambda, away_lambda = _elo_to_lambda(home.elo_rating, away.elo_rating)

    factors = _factors_breakdown(home, away, home_lambda, away_lambda, None, None, {"sample": 0, "source": "none"})

    assert factors["form"]["applied"] is False
    assert factors["form"]["diff"] is None
    assert factors["h2h"]["sample"] == 0
    assert factors["h2h"]["source"] == "none"


def test_factors_breakdown_with_no_h2h():
    """无 H2H 数据时 sample=0."""
    home = Team(id=1, fifa_code="AAA", name_zh="A", name_en="A", group_name="A", elo_rating=1500)
    away = Team(id=2, fifa_code="BBB", name_zh="B", name_en="B", group_name="A", elo_rating=1500)
    from app.services.prediction import _elo_to_lambda
    home_lambda, away_lambda = _elo_to_lambda(home.elo_rating, away.elo_rating)

    factors = _factors_breakdown(home, away, home_lambda, away_lambda, None, None, {"sample": 0, "source": "none"})

    assert factors["h2h"]["sample"] == 0
    assert factors["h2h"]["home_wins"] == 0
    assert factors["h2h"]["source"] == "none"


def test_factors_breakdown_elo_diff_calculation():
    """Elo diff 应为 home - away."""
    home = Team(id=1, fifa_code="A", name_zh="A", name_en="A", group_name="A", elo_rating=2000)
    away = Team(id=2, fifa_code="B", name_zh="B", name_en="B", group_name="A", elo_rating=1800)
    from app.services.prediction import _elo_to_lambda
    home_lambda, away_lambda = _elo_to_lambda(home.elo_rating, away.elo_rating)

    factors = _factors_breakdown(home, away, home_lambda, away_lambda, None, None, {"sample": 0, "source": "none"})

    assert factors["elo"]["diff"] == 200  # 2000 - 1800
    # contribution = (200 + 60) * 0.0035 = 0.91
    assert abs(factors["elo"]["contribution_to_lambda"] - 0.91) < 0.001


# =============== 集成测试 ===============
def test_predict_match_includes_factors_breakdown(db_session, sample_breakdown_match):
    """predict_match 输出应包含 factors_breakdown 字段."""
    match, home, away = sample_breakdown_match
    pred = predict_match(home, away, match, db=db_session)

    assert pred.factors_breakdown is not None
    assert "elo" in pred.factors_breakdown
    assert "form" in pred.factors_breakdown
    assert "h2h" in pred.factors_breakdown
    assert "lambda" in pred.factors_breakdown


@pytest.fixture
def sample_breakdown_match(db_session):
    """构造一个简单的球队+比赛（用于 breakdown 集成测试）."""
    from app.models import Match, Stadium
    home = Team(
        id=20, fifa_code="ENG", name_zh="英格兰", name_en="England",
        group_name="K", flag_emoji="🏴", fifa_rank=5, elo_rating=1700,
        recent_form_points=10, recent_goal_diff=3,
    )
    away = Team(
        id=21, fifa_code="CRO", name_zh="克罗地亚", name_en="Croatia",
        group_name="K", flag_emoji="🇭🇷", fifa_rank=10, elo_rating=1680,
        recent_form_points=7, recent_goal_diff=1,
    )
    stadium = Stadium(
        id=20, name_zh="Test", name_en="Test",
        city="Test", country="Test", timezone="UTC",
    )
    match = Match(
        id=20, match_number=20, stage="小组赛", group_name="K", round_number=1,
        kickoff_at=__import__("datetime").datetime(2026, 6, 15, 18, 0),
        stadium_id=20, home_team_id=20, away_team_id=21,
        status="scheduled", data_source="manual",
    )
    db_session.add_all([home, away, stadium, match])
    db_session.commit()
    return match, home, away
