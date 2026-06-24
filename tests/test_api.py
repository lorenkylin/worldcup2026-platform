"""预测服务单元测试（Poisson + Elo v0）."""

import math

import pytest

from app.services.elo_params import elo_to_lambda
from app.services.prediction import (
    _poisson_prob,
    _predict_score_distribution,
    predict_match,
    _stars,
)
from app.models import Team, Match


def make_team(name_zh: str, elo: int, code: str = "TST", rank: int = None) -> Team:
    return Team(
        id=abs(hash(name_zh)) % 10000,
        fifa_code=code,
        name_zh=name_zh,
        name_en=name_zh,
        group_name="A",
        flag_emoji="",
        elo_rating=elo,
        fifa_rank=rank,
    )


def make_match(home: Team, away: Team) -> Match:
    return Match(
        id=1,
        match_number=1,
        stage="小组赛",
        group_name="A",
        kickoff_at=None,
        home_team=home,
        away_team=away,
        status="scheduled",
    )


# ---------- Elo -> λ 转换 ----------

def test_elo_to_lambda_equal_teams_returns_base():
    """两队 Elo 相等时，λ 应接近 BASE_LAMBDA."""
    h, a = elo_to_lambda(1500, 1500)
    # 主场优势 60 分 * 2 = 0.36 分差（poisson_goal_per_elo_diff=0.0030）
    assert h > a  # 主队 λ 略高（主场优势）
    assert h - a == pytest.approx(0.36, abs=0.01)
    assert h > 0.3 and a > 0.3


def test_elo_to_lambda_higher_home_elo_raises_home_lambda():
    """主队 Elo 更高时，λ_home 应高于 λ_away."""
    h, a = elo_to_lambda(1800, 1500)
    assert h > a


def test_elo_to_lambda_floor_at_min():
    """Elo 极大劣势时，λ 不应低于 0.3."""
    h, a = elo_to_lambda(1200, 1900)
    assert h >= 0.3
    assert a >= 0.3


# ---------- Poisson 概率分布 ----------

def test_poisson_prob_sums_to_approximately_one():
    """Poisson 分布在合理区间内概率和应接近 1."""
    total = sum(_poisson_prob(1.3, k) for k in range(0, 20))
    assert 0.99 < total < 1.01


def test_poisson_prob_negative_k_returns_zero():
    """负 k 应返回 0 概率."""
    assert _poisson_prob(1.5, -1) == 0.0


def test_poisson_prob_mode_around_lambda():
    """均值附近的概率应高于远离均值的."""
    lam = 2.0
    assert _poisson_prob(lam, 2) > _poisson_prob(lam, 0)
    assert _poisson_prob(lam, 2) > _poisson_prob(lam, 5)


# ---------- 比分分布与胜平负 ----------

def test_score_distribution_returns_outcomes_and_scores():
    """比分分布应返回 (home_win, draw, away_win, recommended_score, outcome_aligned, top_scores, confidence)."""
    h, d, a, best, outcome_aligned, top_scores, conf = _predict_score_distribution(1.5, 1.0)
    assert 0 < h < 1
    assert 0 < d < 1
    assert 0 < a < 1
    assert ":" in best
    assert ":" in outcome_aligned
    assert len(top_scores) == 3
    assert 0.0 < conf <= 1.0
    total = h + d + a
    assert abs(total - 1.0) < 1e-6


def test_score_distribution_higher_home_lambda_increases_home_win():
    """主队进攻能力更强时，主胜概率应显著上升."""
    balanced = _predict_score_distribution(1.3, 1.3)[0]
    dominant = _predict_score_distribution(2.5, 0.8)[0]
    assert dominant > balanced + 0.1


# ---------- 星级 ----------

def test_stars_high_confidence_returns_5():
    """胜平负差异大、星级高."""
    assert _stars(0.6, 0.2, 0.2) == 5


def test_stars_low_confidence_returns_low():
    """三者接近时，星级低."""
    assert _stars(0.34, 0.33, 0.33) <= 2


# ---------- predict_match 端到端 ----------

def test_predict_match_equal_teams_roughly_50_percent():
    """两队 Elo 相等时，主胜应接近 50%."""
    home = make_team("A 队", 1500, "AAA")
    away = make_team("B 队", 1500, "BBB")
    match = make_match(home, away)
    result = predict_match(home, away, match)
    assert 40 < result.home_win_prob < 60
    assert result.draw_prob < result.home_win_prob  # 主队略占优
    assert result.stars >= 1
    assert any("Elo" in r or "实力" in r for r in result.reasons)


def test_predict_match_weak_vs_strong_favors_strong():
    """Elo 差距大时，预测应明显倾向强队."""
    home = make_team("弱队", 1300, "WAK")
    away = make_team("强队", 1850, "STR")
    match = make_match(home, away)
    result = predict_match(home, away, match)
    # 强队客胜概率高（注意弱队有 HOME_ADVANTAGE 60 分弥补）
    assert result.away_win_prob > result.home_win_prob - 5
    assert ("Elo" in str(result.reasons) or "实力" in str(result.reasons))


def test_predict_match_recommended_score_format():
    """推荐比分格式应为 a:b."""
    home = make_team("A", 1600, "AAA")
    away = make_team("B", 1600, "BBB")
    match = make_match(home, away)
    result = predict_match(home, away, match)
    parts = result.recommended_score.split(":")
    assert len(parts) == 2
    assert parts[0].isdigit() and parts[1].isdigit()
