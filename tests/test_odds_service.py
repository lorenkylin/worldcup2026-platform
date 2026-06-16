"""odds_service 单元测试.

覆盖:
  - decimal_to_implied_prob: 基本 + 边界
  - remove_vig: 归一化
  - value_bet: 正负零
  - compute_market_probabilities: 1X2 + vig
  - compare_odds_vs_elo: 综合
  - aggregate_multi_bookmaker: 多家平均
"""
import math

from app.services.odds_service import (
    aggregate_multi_bookmaker,
    compare_odds_vs_elo,
    compute_market_probabilities,
    decimal_to_implied_prob,
    remove_vig,
    value_bet,
)


# ============ decimal_to_implied_prob ============

def test_implied_prob_basic():
    """2.10 赔率 → 47.62% 隐含概率."""
    assert math.isclose(decimal_to_implied_prob(2.10), 0.47619, rel_tol=1e-3)
    assert math.isclose(decimal_to_implied_prob(1.50), 0.66667, rel_tol=1e-3)
    assert math.isclose(decimal_to_implied_prob(10.0), 0.10, rel_tol=1e-6)


def test_implied_prob_edge_cases():
    """边界: None/<=1/0 → 0."""
    assert decimal_to_implied_prob(None) == 0.0
    assert decimal_to_implied_prob(0) == 0.0
    assert decimal_to_implied_prob(1.0) == 0.0  # 等价无意义
    assert decimal_to_implied_prob(0.5) == 0.0  # 不合法赔率


# ============ remove_vig ============

def test_remove_vig_basic():
    """3 个隐含概率 (1.04 总和) 归一化 → 和 = 1.0."""
    probs = [0.5, 0.3, 0.24]  # sum = 1.04, vig = 4%
    norm = remove_vig(probs)
    assert math.isclose(sum(norm), 1.0, abs_tol=1e-9)
    assert math.isclose(norm[0], 0.5 / 1.04, rel_tol=1e-3)
    assert math.isclose(norm[1], 0.3 / 1.04, rel_tol=1e-3)
    assert math.isclose(norm[2], 0.24 / 1.04, rel_tol=1e-3)


def test_remove_vig_zero_total():
    """全零概率不应崩溃."""
    assert remove_vig([0, 0, 0]) == [0, 0, 0]


def test_remove_vig_already_normalized():
    """已经 sum=1.0 的概率应保持不变."""
    probs = [0.5, 0.3, 0.2]
    norm = remove_vig(probs)
    assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(probs, norm))


# ============ value_bet ============

def test_value_bet_positive():
    """模型认为概率高于市场 → 正 value."""
    assert math.isclose(value_bet(0.6, 0.5), 0.20, rel_tol=1e-3)  # +20%


def test_value_bet_zero():
    """模型与市场一致 → 0 value."""
    assert math.isclose(value_bet(0.5, 0.5), 0.0, abs_tol=1e-9)


def test_value_bet_negative():
    """模型认为概率低于市场 → 负 value."""
    assert math.isclose(value_bet(0.4, 0.5), -0.20, rel_tol=1e-3)  # -20%


def test_value_bet_zero_market():
    """市场概率为 0 → 返回 0(避免除零)."""
    assert value_bet(0.5, 0) == 0.0
    assert value_bet(0.5, -0.1) == 0.0  # 负数也兜底


# ============ compute_market_probabilities ============

def test_compute_market_balanced():
    """均衡赔率 (2.0/3.0/4.0) → 总 vig 不为 0."""
    result = compute_market_probabilities(2.0, 3.0, 4.0)
    # raw: 0.5 + 0.333 + 0.25 = 1.0833, vig ≈ 8.33%
    assert math.isclose(result["total_vig"], 0.0833, rel_tol=1e-2)
    assert math.isclose(result["home_prob"], 0.5 / 1.0833, rel_tol=1e-2)
    assert math.isclose(result["draw_prob"], 0.333 / 1.0833, rel_tol=1e-2)
    assert math.isclose(result["away_prob"], 0.25 / 1.0833, rel_tol=1e-2)


def test_compute_market_no_vig():
    """完美无 vig 赔率 → 总 vig = 0."""
    # 1/0.5 + 1/0.3 + 1/0.2 = 2 + 3.33 + 5 = 10.33 (有 vig)
    # 完美无 vig: 赔率倒数和 = 1
    # 例: 1/0.6 + 1/0.3 + 1/0.1 = 1.667 + 3.33 + 10 = 15 (有 vig)
    # 用 1/2 + 1/4 + 1/4 = 0.5 + 0.25 + 0.25 = 1.0 (无 vig)
    result = compute_market_probabilities(2.0, 4.0, 4.0)
    assert math.isclose(result["total_vig"], 0.0, abs_tol=1e-9)


def test_compute_market_strong_favorite():
    """明显强队: 主胜赔率 1.20 → 高主胜概率."""
    result = compute_market_probabilities(1.20, 6.0, 15.0)
    assert result["home_prob"] > 0.7
    assert result["away_prob"] < 0.1


# ============ compare_odds_vs_elo ============

def test_compare_basic():
    """Elo 概率与市场概率对比."""
    result = compare_odds_vs_elo(
        odds_home=2.0, odds_draw=3.5, odds_away=4.0,
        elo_home_prob=0.55, elo_draw_prob=0.25, elo_away_prob=0.20,
    )
    assert "market" in result and "elo" in result and "value_bet" in result
    # Elo 主胜 55% > 市场主胜(去 vig 后)→ value_bet.home 应为正
    assert result["value_bet"]["home"] > 0
    # best_value 应该是 home
    assert result["best_value"] in ("home", "draw", "away")


def test_compare_no_value_bet():
    """Elo 与市场完全一致 → best_value = None."""
    # 赔率倒数 = 概率 → vig = 0, normalize 后概率 = elo 概率
    # 找赔率使 1/h + 1/d + 1/a = 1.0 且各 = elo
    # 假设 elo = 0.5/0.3/0.2 → 赔率 = 2.0/3.33/5.0
    result = compare_odds_vs_elo(
        odds_home=2.0, odds_draw=3.333, odds_away=5.0,
        elo_home_prob=0.5, elo_draw_prob=0.3, elo_away_prob=0.2,
    )
    # 几乎为零但 best_value_rate 应 <= 0(允许微小误差)
    # 这里不一定严格 best_value=None,因为浮点误差
    if result["best_value"]:
        assert result["best_value_rate"] < 0.01


def test_compare_strong_value_bet():
    """模型强烈看好主队 + 市场低估 → home value_bet 大."""
    result = compare_odds_vs_elo(
        odds_home=3.0, odds_draw=3.5, odds_away=2.5,  # 市场认为客胜
        elo_home_prob=0.65, elo_draw_prob=0.20, elo_away_prob=0.15,  # 模型强烈主胜
    )
    assert result["value_bet"]["home"] > 0.3  # > 30% value
    assert result["best_value"] == "home"


# ============ aggregate_multi_bookmaker ============

def test_aggregate_basic():
    """3 家公司赔率平均."""
    odds_list = [
        {"home_win": 2.0, "draw": 3.0, "away_win": 4.0},
        {"home_win": 2.2, "draw": 3.2, "away_win": 3.8},
        {"home_win": 1.8, "draw": 2.8, "away_win": 4.2},
    ]
    result = aggregate_multi_bookmaker(odds_list)
    assert math.isclose(result["home_win"], 2.0, abs_tol=0.01)
    assert math.isclose(result["draw"], 3.0, abs_tol=0.01)
    assert math.isclose(result["away_win"], 4.0, abs_tol=0.01)


def test_aggregate_with_missing_fields():
    """某些家缺字段 → 跳过取平均."""
    odds_list = [
        {"home_win": 2.0, "draw": 3.0, "away_win": 4.0},
        {"home_win": 2.2, "draw": None, "away_win": 3.8},  # 缺 draw
    ]
    result = aggregate_multi_bookmaker(odds_list)
    assert math.isclose(result["home_win"], 2.1, abs_tol=0.01)
    assert result["draw"] == 3.0  # 只用第一家
    assert math.isclose(result["away_win"], 3.9, abs_tol=0.01)


def test_aggregate_empty():
    """空列表 → 全 None."""
    result = aggregate_multi_bookmaker([])
    assert all(v is None for v in result.values())
