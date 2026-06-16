"""M3 赔率归一化 + value bet 计算服务.

核心算法:
  1. decimal_to_implied_prob: decimal 赔率 → 隐含概率(去 vig 前)
  2. remove_vig: 归一化消除博彩公司利润(经典做法)
  3. value_bet: 模型概率 vs 市场隐含概率,识别价值投注
  4. compute_market_probabilities: 1X2 隐含概率聚合(支持多 bookmaker 平均)

参考:
  - Kelly Criterion (1956)
  - "Trading Bases" by Joe Peta - vig removal methods
"""
from typing import Dict, List, Optional


def decimal_to_implied_prob(odds: float) -> float:
    """decimal 赔率 → 隐含概率(去 vig 前).

    例如 2.10 → 0.4762 (47.62%), 1.50 → 0.6667 (66.67%).
    赔率越低,隐含概率越高.
    """
    if odds is None or odds <= 1.0:
        return 0.0
    return 1.0 / odds


def remove_vig(probs: List[float]) -> List[float]:
    """归一化消除博彩公司利润(vig).

    简单加性归一化: 把三个隐含概率按比例缩放到 sum=1.0.
    适用于 1X2(3 个结果)等"互斥穷尽"事件.

    Args:
        probs: 原始隐含概率列表,sum > 1.0(含 vig)
    Returns:
        归一化后概率列表,sum = 1.0
    """
    total = sum(probs)
    if total == 0:
        return probs
    return [p / total for p in probs]


def value_bet(model_prob: float, market_prob: float) -> float:
    """价值投注率: 模型概率 / 市场隐含概率 - 1.

    > 0: 模型认为此结果被市场低估(value bet)
    < 0: 模型认为此结果被市场高估(避开)
    = 0: 模型与市场一致

    业界阈值:
      > +5%:  强价值,值得投注(注意 Kelly 比例)
      0 ~ +5%: 边缘价值,慎投
      < 0:    不投

    注意: 此函数仅返回"理论价值率",不构成投注建议(展示用).
    """
    if market_prob <= 0:
        return 0.0
    return model_prob / market_prob - 1.0


def compute_market_probabilities(
    home_odds: float,
    draw_odds: float,
    away_odds: float,
) -> Dict[str, float]:
    """1X2 赔率 → 归一化概率(去 vig 后).

    Args:
        home_odds/draw_odds/away_odds: 三种结果的 decimal 赔率
    Returns:
        {home_prob, draw_prob, away_prob, total_vig}
        total_vig: 总隐含概率(>1.0 部分即博彩公司利润),0.05=5% 利润
    """
    raw = [
        decimal_to_implied_prob(home_odds),
        decimal_to_implied_prob(draw_odds),
        decimal_to_implied_prob(away_odds),
    ]
    normalized = remove_vig(raw)
    total_vig = sum(raw) - 1.0  # 博彩公司理论利润
    return {
        "home_prob": normalized[0],
        "draw_prob": normalized[1],
        "away_prob": normalized[2],
        "total_vig": round(total_vig, 4),
    }


def compare_odds_vs_elo(
    odds_home: float,
    odds_draw: float,
    odds_away: float,
    elo_home_prob: float,
    elo_draw_prob: float,
    elo_away_prob: float,
) -> Dict:
    """赔率隐含概率 vs Elo 模型概率 → value bet 对比.

    Args:
        odds_*: 三种结果的 decimal 赔率(必填)
        elo_*: Elo 模型预测的三种概率(必填,sum=1.0)
    Returns:
        {
          market: {home_prob, draw_prob, away_prob, total_vig},
          elo: {home_prob, draw_prob, away_prob},
          value_bet: {home, draw, away},   # value_bet 率
          best_value: "home"/"draw"/"away"/None,
          best_value_rate: float,
        }
    """
    market = compute_market_probabilities(odds_home, odds_draw, odds_away)

    vb_home = value_bet(elo_home_prob, market["home_prob"])
    vb_draw = value_bet(elo_draw_prob, market["draw_prob"])
    vb_away = value_bet(elo_away_prob, market["away_prob"])

    # 找最大 value bet(>0)
    candidates = {
        "home": vb_home,
        "draw": vb_draw,
        "away": vb_away,
    }
    best = max(candidates.items(), key=lambda kv: kv[1])
    if best[1] <= 0:
        best_value = None
        best_value_rate = 0.0
    else:
        best_value = best[0]
        best_value_rate = round(best[1], 4)

    return {
        "market": {k: round(v, 4) for k, v in market.items()},
        "elo": {
            "home_prob": round(elo_home_prob, 4),
            "draw_prob": round(elo_draw_prob, 4),
            "away_prob": round(elo_away_prob, 4),
        },
        "value_bet": {
            "home": round(vb_home, 4),
            "draw": round(vb_draw, 4),
            "away": round(vb_away, 4),
        },
        "best_value": best_value,
        "best_value_rate": best_value_rate,
    }


def aggregate_multi_bookmaker(odds_list: List[Dict[str, Optional[float]]]) -> Dict[str, Optional[float]]:
    """多博彩公司赔率 → 算术平均赔率.

    Args:
        odds_list: [{"home_win": 2.10, "draw": 3.40, "away_win": 3.60}, ...]
                   允许个别字段为 None,跳过取平均
    Returns:
        {"home_win": avg, "draw": avg, "away_win": avg, "over_2_5": avg, "under_2_5": avg}
    """
    if not odds_list:
        return {"home_win": None, "draw": None, "away_win": None,
                "over_2_5": None, "under_2_5": None}

    fields = ("home_win", "draw", "away_win", "over_2_5", "under_2_5")
    result: Dict[str, Optional[float]] = {}
    for field in fields:
        values = [o.get(field) for o in odds_list if o.get(field) is not None]
        if values:
            result[field] = round(sum(values) / len(values), 2)
        else:
            result[field] = None
    return result
