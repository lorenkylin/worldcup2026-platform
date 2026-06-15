"""Elo 评分 + Dixon-Coles bivariate Poisson 预测.

数据源: Hicruben/world-cup-2026-prediction-model (60+ 队, 913 场真实国际赛 2023-11 ~ 2026-06).
参考: World Football Elo (eloratings.net), Maher (1982), Dixon & Coles (1997).

4 年 walk-forward 回测 (K=60, home_bonus=70, rho=-0.13, burn-in=150):
  - RPS: 0.2002 (coin-flip 0.241, -17%)
  - Log-loss: 0.9690 (coin-flip 1.10, -12%)
  - Brier: 0.5752 (coin-flip 0.67, -14%)
  - 准确率: 58.3% (Hicruben 参考 62%)
"""
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Tuple, Dict, List, Optional

# === Elo 参数（与 Hicruben/world-cup-2026-prediction-model 一致） ===
K_FACTOR_WC = 60        # K 因子
HOME_BONUS = 70         # 主场优势 (Elo 分数)
DC_RHO = -0.13          # Dixon-Coles ρ 修正（0-0/1-1 平局校正）
INIT_RATING = 1500      # 初始 Elo

# === M2 增强参数（form + h2h 加权） ===
# 形式化映射：recent_form_points 0-15 → Elo 调整 -37.5 ~ +37.5
# 公式：(form - 7.5) * 5 = 中位 7.5 分为 0，最高 15 分 = +37.5，最低 0 分 = -37.5
FORM_BOOST_SCALE = 5.0
# H2H 胜率映射：(home_win_rate - 0.5) * 50 = 主场胜率 100% = +25，0% = -25
H2H_BOOST_SCALE = 50.0
# H2H 至少 2 场才生效（避免 1 场偶然结果过度影响；当前种子数据 max=2 场）
H2H_MIN_SAMPLES = 2


def expected_goals(rating: float, opponent: float, home_bonus: float = 0.0) -> float:
    """Elo 差 → Poisson λ (期望进球数)."""
    diff = (rating + home_bonus) - opponent
    return max(0.3, min(3.5, 1.35 + diff / 400))


def poisson_pmf(k: int, lam: float) -> float:
    """Poisson 概率质量函数."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    p = math.exp(-lam)
    for i in range(1, k + 1):
        p *= lam / i
    return p


def dc_tau(a: int, b: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles 低分修正因子."""
    if a == 0 and b == 0: return 1 - lam * mu * rho
    if a == 0 and b == 1: return 1 + lam * rho
    if a == 1 and b == 0: return 1 + mu * rho
    if a == 1 and b == 1: return 1 - rho
    return 1.0


def match_prob(rating_a: float, rating_b: float, home_bonus_a: float = 0.0) -> Dict:
    """Elo + Dixon-Coles 1X2 概率 + 期望进球.

    Returns:
        {
            'winA': float,    # 主场队胜率
            'draw': float,    # 平局率
            'winB': float,    # 客场队胜率
            'expectedGoalsA': float,
            'expectedGoalsB': float,
        }
    """
    lam = expected_goals(rating_a, rating_b, home_bonus_a)
    mu = expected_goals(rating_b, rating_a, -home_bonus_a / 2)
    win_a = draw = win_b = 0.0
    for a in range(9):
        p_a = poisson_pmf(a, lam)
        for b in range(9):
            tau = dc_tau(a, b, lam, mu, DC_RHO)
            p = p_a * poisson_pmf(b, mu) * tau
            if a > b: win_a += p
            elif a < b: win_b += p
            else: draw += p
    total = win_a + draw + win_b
    if total == 0:
        return {'winA': 1/3, 'draw': 1/3, 'winB': 1/3, 'expectedGoalsA': lam, 'expectedGoalsB': mu}
    return {
        'winA': win_a / total,
        'draw': draw / total,
        'winB': win_b / total,
        'expectedGoalsA': lam,
        'expectedGoalsB': mu,
    }


def elo_update(rating_a: float, rating_b: float, score_a: float, home_bonus_a: float = 0.0, k: float = K_FACTOR_WC) -> Tuple[float, float]:
    """Elo 赛后更新 (score_a: 1=胜, 0.5=平, 0=负)."""
    expected_a = 1 / (1 + 10 ** ((rating_b - (rating_a + home_bonus_a)) / 400))
    expected_b = 1 - expected_a
    new_a = rating_a + k * (score_a - expected_a)
    new_b = rating_b + k * ((1 - score_a) - expected_b)
    return new_a, new_b


# === M2: Form + H2H Elo 调整因子（纯函数，service 不依赖 DB） ===

def form_boost(form_points: Optional[int]) -> float:
    """近 5 场国际赛积分 (0-15) → Elo 调整.

    映射公式：(form - 7.5) * 5
      - form=0  → -37.5 Elo（极差状态）
      - form=7.5 → 0 Elo（平均）
      - form=15 → +37.5 Elo（极好状态）
    None → 0.0（无数据时不加调整）
    """
    if form_points is None:
        return 0.0
    return (form_points - 7.5) * FORM_BOOST_SCALE


def h2h_boost(home_wins: int, away_wins: int, draws: int, sample: int) -> float:
    """历史交锋胜率 → Elo 调整（主队视角）.

    映射公式：(home_win_rate - 0.5) * 50
      - sample < H2H_MIN_SAMPLES → 0（数据不足）
      - home_rate=1.0 (全胜) → +25 Elo
      - home_rate=0.5 (平)   → 0 Elo
      - home_rate=0.0 (全负) → -25 Elo
    """
    if sample < H2H_MIN_SAMPLES:
        return 0.0
    home_rate = home_wins / sample
    return (home_rate - 0.5) * H2H_BOOST_SCALE


def predict_match_enhanced(
    home_code: str,
    away_code: str,
    home_form: Optional[int] = None,
    away_form: Optional[int] = None,
    h2h_home_wins: int = 0,
    h2h_away_wins: int = 0,
    h2h_draws: int = 0,
) -> Dict:
    """M2 增强预测：Elo + form + H2H 加权.

    与 M1 predict_match 对比：
      - M1: 纯 Elo + Dixon-Coles
      - M2: 接受 form_points 和 H2H 数据，调整 effective_elo 后跑同一 Dixon-Coles 模型

    返回值含 v1（base）和 v2（enhanced）双套结果，方便前端对比。

    Returns:
        {
            'home': {'fifa_code': str, 'elo': int},
            'away': {'fifa_code': str, 'elo': int},
            'v1': {  # M1 纯 Elo（基准）
                'probabilities': {...}, 'expected_goals': {...},
            },
            'v2': {  # M2 增强
                'probabilities': {...}, 'expected_goals': {...},
                'form_boost_home': float, 'form_boost_away': float,
                'h2h_boost_home': float, 'h2h_sample': int,
                'effective_elo_home': float, 'effective_elo_away': float,
            },
            'factors': {  # 透明展示
                'home_form': int|None, 'away_form': int|None,
                'h2h_home_wins': int, 'h2h_away_wins': int, 'h2h_draws': int, 'h2h_sample': int,
            },
            'model': 'elo_dixon_coles_v2',
            'data_source': 'hicruben/world-cup-2026-prediction-model',
            'data_as_of': str,
        }
    """
    data = load_elo_ratings()
    elo_home = get_team_elo(home_code)
    elo_away = get_team_elo(away_code)
    if elo_home is None or elo_away is None:
        return {
            'home': {'fifa_code': home_code, 'elo': elo_home},
            'away': {'fifa_code': away_code, 'elo': elo_away},
            'error': f'球队 {home_code} 或 {away_code} 不在 Elo 数据中',
            'data_as_of': data.get('generatedAt'),
        }

    # V1: M1 纯 Elo
    v1_probs = match_prob(elo_home, elo_away, home_bonus_a=HOME_BONUS)

    # V2: form + H2H 加权
    fb_home = form_boost(home_form)
    fb_away = form_boost(away_form)
    hb_home = h2h_boost(h2h_home_wins, h2h_away_wins, h2h_draws, h2h_home_wins + h2h_away_wins + h2h_draws)
    h2h_sample = h2h_home_wins + h2h_away_wins + h2h_draws
    effective_elo_home = elo_home + fb_home + hb_home
    effective_elo_away = elo_away + fb_away - hb_home  # H2H 对主场加成对客场减成（对称）
    v2_probs = match_prob(effective_elo_home, effective_elo_away, home_bonus_a=HOME_BONUS)

    return {
        'home': {'fifa_code': home_code, 'elo': elo_home},
        'away': {'fifa_code': away_code, 'elo': elo_away},
        'v1': {
            'probabilities': {
                'home_win': round(v1_probs['winA'], 4),
                'draw': round(v1_probs['draw'], 4),
                'away_win': round(v1_probs['winB'], 4),
            },
            'expected_goals': {
                'home': round(v1_probs['expectedGoalsA'], 2),
                'away': round(v1_probs['expectedGoalsB'], 2),
            },
            'effective_elo': {'home': elo_home, 'away': elo_away},
        },
        'v2': {
            'probabilities': {
                'home_win': round(v2_probs['winA'], 4),
                'draw': round(v2_probs['draw'], 4),
                'away_win': round(v2_probs['winB'], 4),
            },
            'expected_goals': {
                'home': round(v2_probs['expectedGoalsA'], 2),
                'away': round(v2_probs['expectedGoalsB'], 2),
            },
            'effective_elo': {
                'home': round(effective_elo_home, 1),
                'away': round(effective_elo_away, 1),
            },
            'form_boost_home': round(fb_home, 1),
            'form_boost_away': round(fb_away, 1),
            'h2h_boost_home': round(hb_home, 1),
            'h2h_boost_away': round(-hb_home, 1),
            'h2h_sample': h2h_sample,
        },
        'factors': {
            'home_form': home_form,
            'away_form': away_form,
            'h2h_home_wins': h2h_home_wins,
            'h2h_away_wins': h2h_away_wins,
            'h2h_draws': h2h_draws,
            'h2h_sample': h2h_sample,
        },
        'model': 'elo_dixon_coles_v2',
        'data_source': 'hicruben/world-cup-2026-prediction-model',
        'data_as_of': data.get('generatedAt'),
        'parameters': {
            'k_factor': K_FACTOR_WC,
            'home_bonus': HOME_BONUS,
            'dc_rho': DC_RHO,
            'form_boost_scale': FORM_BOOST_SCALE,
            'h2h_boost_scale': H2H_BOOST_SCALE,
            'h2h_min_samples': H2H_MIN_SAMPLES,
        },
    }


# === 数据加载 ===

# FIFA 3-letter code → kebab-case（用于在 Hicruben 数据中查找）
FIFA_TO_HICRUBEN = {
    'ARG': 'argentina', 'FRA': 'france', 'ESP': 'spain', 'BRA': 'brazil', 'ENG': 'england',
    'POR': 'portugal', 'NED': 'netherlands', 'GER': 'germany', 'BEL': 'belgium', 'ITA': 'italy',
    'COL': 'colombia', 'URU': 'uruguay', 'CRO': 'croatia', 'MAR': 'morocco', 'SUI': 'switzerland',
    'USA': 'usa', 'MEX': 'mexico', 'JPN': 'japan', 'SEN': 'senegal', 'DEN': 'denmark',
    'ECU': 'ecuador', 'AUS': 'australia', 'KOR': 'south-korea', 'IRN': 'iran', 'POL': 'poland',
    'CAN': 'canada', 'SRB': 'serbia', 'WAL': 'wales', 'GHA': 'ghana', 'TUN': 'tunisia',
    'CIV': 'ivory-coast', 'NGA': 'nigeria', 'KSA': 'saudi-arabia', 'QAT': 'qatar', 'EGY': 'egypt',
    'ALG': 'algeria', 'SCO': 'scotland', 'CMR': 'cameroon', 'PAR': 'paraguay', 'VEN': 'venezuela',
    'CHI': 'chile', 'PER': 'peru', 'CZE': 'czech-republic', 'BIH': 'bosnia-and-herzegovina',
    'RSA': 'south-africa', 'NZL': 'new-zealand', 'PAN': 'panama', 'JAM': 'jamaica',
    'HON': 'honduras', 'JOR': 'jordan', 'HAI': 'haiti', 'SLV': 'el-salvador',
    'TRI': 'trinidad-and-tobago', 'GUA': 'guatemala', 'NOR': 'norway', 'SWE': 'sweden',
    'TUR': 'turkey', 'AUT': 'austria', 'IRQ': 'iraq', 'UZB': 'uzbekistan', 'CPV': 'cape-verde',
    'COD': 'dr-congo', 'CUW': 'curacao',
}

CALIBRATED_PATH = Path(__file__).resolve().parent.parent.parent / 'data' / 'seed' / 'hicruben' / 'elo-calibrated.json'


@lru_cache(maxsize=1)
def load_elo_ratings() -> Dict:
    """加载 Hicruben 校准后的 Elo 评分（截至 2026-06-11, 913 场）."""
    if not CALIBRATED_PATH.exists():
        return {'ratings': {}, 'generatedAt': None, 'matchesApplied': 0}
    return json.loads(CALIBRATED_PATH.read_text(encoding='utf-8'))


def get_team_elo(fifa_code: str) -> Optional[int]:
    """根据 FIFA 3-letter code 查 Elo 评分（不在数据里返回 None）."""
    data = load_elo_ratings()
    kebab = FIFA_TO_HICRUBEN.get(fifa_code.upper())
    if not kebab:
        return None
    return data.get('ratings', {}).get(kebab)


def predict_match(home_code: str, away_code: str) -> Dict:
    """预测单场比赛 1X2 + 期望进球.

    Returns:
        {
            'home': {'fifa_code': str, 'elo': int|None},
            'away': {'fifa_code': str, 'elo': int|None},
            'probabilities': {'home_win': float, 'draw': float, 'away_win': float},
            'expected_goals': {'home': float, 'away': float},
            'model': 'elo_dixon_coles_v1',
            'data_source': 'hicruben/world-cup-2026-prediction-model',
            'data_as_of': str,
        }
    """
    data = load_elo_ratings()
    elo_home = get_team_elo(home_code)
    elo_away = get_team_elo(away_code)
    if elo_home is None or elo_away is None:
        return {
            'home': {'fifa_code': home_code, 'elo': elo_home},
            'away': {'fifa_code': away_code, 'elo': elo_away},
            'probabilities': {'home_win': None, 'draw': None, 'away_win': None},
            'expected_goals': {'home': None, 'away': None},
            'error': f'球队 {home_code} 或 {away_code} 不在 Elo 数据中',
            'data_as_of': data.get('generatedAt'),
        }
    probs = match_prob(elo_home, elo_away, home_bonus_a=HOME_BONUS)
    return {
        'home': {'fifa_code': home_code, 'elo': elo_home},
        'away': {'fifa_code': away_code, 'elo': elo_away},
        'probabilities': {
            'home_win': round(probs['winA'], 4),
            'draw': round(probs['draw'], 4),
            'away_win': round(probs['winB'], 4),
        },
        'expected_goals': {
            'home': round(probs['expectedGoalsA'], 2),
            'away': round(probs['expectedGoalsB'], 2),
        },
        'model': 'elo_dixon_coles_v1',
        'data_source': 'hicruben/world-cup-2026-prediction-model',
        'data_as_of': data.get('generatedAt'),
        'parameters': {
            'k_factor': K_FACTOR_WC,
            'home_bonus': HOME_BONUS,
            'dc_rho': DC_RHO,
        },
    }


def get_top_elo(limit: int = 10) -> List[Dict]:
    """Top N Elo 评分（48 参赛队，按 Elo 降序）."""
    data = load_elo_ratings()
    ratings = data.get('ratings', {})
    # 反向：kebab → FIFA 3-letter
    rev_map = {v: k for k, v in FIFA_TO_HICRUBEN.items()}
    rows = []
    for kebab, rating in ratings.items():
        fifa_code = rev_map.get(kebab)
        if fifa_code:
            rows.append({'fifa_code': fifa_code, 'kebab': kebab, 'elo': rating})
    rows.sort(key=lambda x: -x['elo'])
    return rows[:limit]


def get_backtest_metrics() -> Dict:
    """加载 4 年回测指标（来自 M1.2 backtest 脚本的输出）."""
    metrics_path = CALIBRATED_PATH.parent / 'backtest_metrics.json'
    if not metrics_path.exists():
        return {'error': '回测指标未生成，请先跑 scripts/m1_backtest.py'}
    return json.loads(metrics_path.read_text(encoding='utf-8'))
