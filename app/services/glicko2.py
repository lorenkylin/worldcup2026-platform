"""Glicko-2 评分系统 (Mark Glickman, 2013).

参考: http://www.glicko.net/glicko/glicko2.pdf
适用: 国际象棋/电竞/团队对抗。优势: 含 RD(评分偏差)能识别"近期数据少/不稳定"。

Glicko-2 关键概念:
  - rating (r): 评分,默认 1500
  - RD (φ): Rating Deviation, 评分偏差,默认 350
  - volatility (σ): 波动率,默认 0.06
  - system constant τ (tau): 控制 volatility 变化的速度,典型 0.2-1.2

与 Elo 对比:
  - Elo 假设评分静态 → 所有队同等可信
  - Glicko-2 的 RD 量化"我们有多确定该队的真实实力"
  - 长期未比赛的队 RD 会"发散",实际预测时使用较宽的区间

参考实现: Tomas Polasek (MIT) 简化版本 + Illinois 算法求 volatility
"""
import math
from typing import Dict, List, Tuple, Optional


# === Glicko-2 系统常量 ===
SCALE = 173.7178  # Glicko-2 与经典 Elo 的尺度转换常数
DEFAULT_RATING = 1500.0
DEFAULT_RD = 350.0
DEFAULT_VOLATILITY = 0.06
DEFAULT_TAU = 0.5  # system constant, 0.2-1.2 之间; 0.5 是通用推荐
EPSILON = 1e-6  # volatility 迭代收敛阈值


# === 工具函数 (Section 3 of Glicko-2 spec) ===

def g(phi: float) -> float:
    """g(φ) = 1 / sqrt(1 + 3φ² / π²)."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi ** 2 / (math.pi ** 2))


def E(mu: float, mu_j: float, phi_j: float) -> float:
    """E(μ, μ_j, φ_j) = 1 / (1 + exp(-g(φ_j) · (μ - μ_j)))."""
    return 1.0 / (1.0 + math.exp(-g(phi_j) * (mu - mu_j)))


def to_glicko2_scale(rating: float, rd: float) -> Tuple[float, float]:
    """Classic Glicko → Glicko-2 尺度: μ = (r - 1500) / 173.7178, φ = RD / 173.7178."""
    return (rating - 1500.0) / SCALE, rd / SCALE


def from_glicko2_scale(mu: float, phi: float) -> Tuple[float, float]:
    """Glicko-2 → Classic Glicko: r = μ · 173.7178 + 1500, RD = φ · 173.7178."""
    return mu * SCALE + 1500.0, phi * SCALE


# === 单局更新 (Section 4 of Glicko-2 spec) ===

def rate_1vs1(
    rating: float,
    rd: float,
    sigma: float,
    opponent_rating: float,
    opponent_rd: float,
    score: float,  # 1=胜, 0.5=平, 0=负
    tau: float = DEFAULT_TAU,
) -> Tuple[float, float, float]:
    """单场对单场更新 (rating, RD, sigma).

    Args:
        rating: 己方 Glicko 评分
        rd: 己方 RD
        sigma: 己方 volatility
        opponent_rating: 对手 Glicko 评分
        opponent_rd: 对手 RD
        score: 1=胜, 0.5=平, 0=负
        tau: 系统常数 (0.2-1.2)

    Returns:
        (new_rating, new_rd, new_sigma)
    """
    mu, phi = to_glicko2_scale(rating, rd)
    mu_j, phi_j = to_glicko2_scale(opponent_rating, opponent_rd)

    # Step 3: v = 1 / (g(φ_j)² · E · (1-E))
    g_j = g(phi_j)
    e_j = E(mu, mu_j, phi_j)
    v = 1.0 / (g_j ** 2 * e_j * (1.0 - e_j))

    # Step 4: Δ = v · g(φ_j) · (score - E)
    delta = v * g_j * (score - e_j)

    # Step 5: 更新 volatility (Illinois 算法, Section 5.1)
    new_sigma = _update_volatility(sigma, phi, v, delta, tau)

    # Step 6: φ* = sqrt(φ² + σ'²)
    phi_star = math.sqrt(phi ** 2 + new_sigma ** 2)

    # Step 7: φ' = 1 / sqrt(1/φ*² + 1/v)
    new_phi = 1.0 / math.sqrt(1.0 / phi_star ** 2 + 1.0 / v)

    # Step 8: μ' = μ + φ'² · g(φ_j) · (score - E)
    new_mu = mu + new_phi ** 2 * g_j * (score - e_j)

    new_rating, new_rd = from_glicko2_scale(new_mu, new_phi)
    return new_rating, new_rd, new_sigma


def _update_volatility(
    sigma: float,
    phi: float,
    v: float,
    delta: float,
    tau: float,
) -> float:
    """Illinois 算法迭代求新 volatility (Section 5.1 of Glicko-2 spec)."""
    # Step 5.1: a = ln(σ²)
    a = math.log(sigma ** 2)

    # Step 5.2: f(x) = (e^x · (δ² - φ² - v - e^x)) / (2 · (φ² + v + e^x)²) - (x - a) / τ²
    def f(x: float) -> float:
        ex = math.exp(x)
        return (ex * (delta ** 2 - phi ** 2 - v - ex)) / (2.0 * (phi ** 2 + v + ex) ** 2) - (x - a) / (tau ** 2)

    # Step 5.3-5.5: 找 A 和 B 边界
    A = a
    if delta ** 2 > phi ** 2 + v:
        B = math.log(delta ** 2 - phi ** 2 - v)
    else:
        k = 1
        # 找 B 使得 f(B) > 0
        while True:
            B_val = a - k * tau
            if f(B_val) < 0:
                k += 1
            else:
                B = B_val
                break

    # Step 5.6-5.7: 迭代求根
    fA, fB = f(A), f(B)
    while abs(B - A) > EPSILON:
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB <= 0:
            A, fA = B, fB
        else:
            fA /= 2.0
        B, fB = C, fC

    return math.exp(A / 2.0)


# === 批量更新 (Glicko-2 spec Section 6) ===

def rate_period(
    rating: float,
    rd: float,
    sigma: float,
    opponents: List[Tuple[float, float, float]],  # [(opp_rating, opp_rd, score), ...]
    tau: float = DEFAULT_TAU,
) -> Tuple[float, float, float]:
    """一个 rating period (通常 1 天/1 周) 内的所有比赛批量更新.

    Args:
        rating: 己方评分
        rd: 己方 RD
        sigma: 己方 volatility
        opponents: 该 period 内所有对手, (rating, RD, score) 三元组
        tau: 系统常数

    Returns:
        (new_rating, new_rd, new_sigma)
    """
    if not opponents:
        # 没有比赛: RD 增大,volatility 不变
        mu, phi = to_glicko2_scale(rating, rd)
        phi_star = math.sqrt(phi ** 2 + sigma ** 2)
        new_rating, new_rd = from_glicko2_scale(mu, phi_star)
        return new_rating, new_rd, sigma

    mu, phi = to_glicko2_scale(rating, rd)
    mu_j_list, phi_j_list, s_list = [], [], []
    for opp_r, opp_rd, score in opponents:
        mu_j, phi_j = to_glicko2_scale(opp_r, opp_rd)
        mu_j_list.append(mu_j)
        phi_j_list.append(phi_j)
        s_list.append(score)

    # Step 3: v = 1 / Σ g(φ_j)² · E_j · (1 - E_j)
    v_inv = 0.0
    for mu_j, phi_j in zip(mu_j_list, phi_j_list):
        g_j = g(phi_j)
        e_j = E(mu, mu_j, phi_j)
        v_inv += g_j ** 2 * e_j * (1.0 - e_j)
    v = 1.0 / v_inv

    # Step 4: Δ = v · Σ g(φ_j) · (s_j - E_j)
    delta_sum = 0.0
    for mu_j, phi_j, s in zip(mu_j_list, phi_j_list, s_list):
        g_j = g(phi_j)
        e_j = E(mu, mu_j, phi_j)
        delta_sum += g_j * (s - e_j)
    delta = v * delta_sum

    # Step 5: 更新 volatility
    new_sigma = _update_volatility(sigma, phi, v, delta, tau)

    # Step 6-7: 更新 phi (RD)
    phi_star = math.sqrt(phi ** 2 + new_sigma ** 2)
    new_phi = 1.0 / math.sqrt(1.0 / phi_star ** 2 + 1.0 / v)

    # Step 8: 更新 mu (rating)
    new_mu = mu + new_phi ** 2 * delta_sum

    new_rating, new_rd = from_glicko2_scale(new_mu, new_phi)
    return new_rating, new_rd, new_sigma


# === 高层 API ===

def predict_outcome(
    rating_a: float,
    rd_a: float,
    rating_b: float,
    rd_b: float,
    home_bonus: float = 0.0,
) -> Dict[str, float]:
    """预测 A vs B 比赛 (A 主场,主场优势加 rating).

    Glicko-2 因为有 RD 概念,可输出"不确定性".
    E_A = 1 / (1 + exp(-g(φ_eff) · (μ_A - μ_B)))
    其中 φ_eff = sqrt(φ_A² + φ_B²) (合并不确定性)

    Returns:
        {
            'win_a': float,    # A 胜率
            'draw': float,     # 平局率 (使用 Elo 平局经验模型, 22% × 总分)
            'win_b': float,    # B 胜率
            'expected_score': float,  # 期望得分
            'uncertainty': float,     # 不确定性 (1-1/φ_eff)
        }
    """
    mu_a, phi_a = to_glicko2_scale(rating_a + home_bonus, rd_a)
    mu_b, phi_b = to_glicko2_scale(rating_b, rd_b)

    g_b = g(phi_b)
    e_a = 1.0 / (1.0 + math.exp(-g_b * (mu_a - mu_b)))

    # 平局率: 国际足球经验值约 22-26%, 实力差越大平局率越低
    # 简化: draw_base = 0.23, 差越大 draw 越低
    rating_diff = abs(rating_a + home_bonus - rating_b)
    draw_prob = max(0.10, 0.26 - rating_diff * 0.0005)

    # win_b = 1 - win_a - draw
    win_b = 1.0 - e_a
    # 把 1-2% 的总概率分配给平局
    if win_b < 0:
        win_b = 0.0
    win_a_no_draw = e_a * (1.0 - draw_prob)
    win_b_no_draw = win_b * (1.0 - draw_prob)

    # 不确定性: 合并 RD
    phi_eff = math.sqrt(phi_a ** 2 + phi_b ** 2)
    uncertainty = min(0.5, phi_eff / 3.0)  # 0(很确定) ~ 0.5(完全随机)

    return {
        'win_a': round(win_a_no_draw, 4),
        'draw': round(draw_prob, 4),
        'win_b': round(win_b_no_draw, 4),
        'expected_score': round(e_a, 4),
        'uncertainty': round(uncertainty, 4),
    }


# === 数据加载 (FIFA code ↔ team name 映射) ===

# FIFA 3-letter code → Hicruben kebab-slug
G2_FIFA_TO_SLUG = {
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
    'TUR': 'turkey',  # 来自 Tuerkiye
}

# 完整 team name → FIFA code (来自 wc2026 seed)
G2_NAME_TO_CODE = {
    'Mexico': 'MEX', 'South Africa': 'RSA', 'South Korea': 'KOR', 'Czech Republic': 'CZE',
    'United States': 'USA', 'Canada': 'CAN', 'Brazil': 'BRA', 'Morocco': 'MAR',
    'Argentina': 'ARG', 'France': 'FRA', 'Spain': 'ESP', 'England': 'ENG',
    'Germany': 'GER', 'Italy': 'ITA', 'Portugal': 'POR', 'Netherlands': 'NED',
    'Belgium': 'BEL', 'Croatia': 'CRO', 'Uruguay': 'URU', 'Colombia': 'COL',
    'Japan': 'JPN', 'Senegal': 'SEN', 'Denmark': 'DEN', 'Ecuador': 'ECU',
    'Switzerland': 'SUI', 'Australia': 'AUS', 'Iran': 'IRN', 'Poland': 'POL',
    'Serbia': 'SRB', 'Wales': 'WAL', 'Ghana': 'GHA', 'Tunisia': 'TUN',
    'Ivory Coast': 'CIV', 'Nigeria': 'NGA', 'Saudi Arabia': 'KSA', 'Qatar': 'QAT',
    'Egypt': 'EGY', 'Algeria': 'ALG', 'Scotland': 'SCO', 'Cameroon': 'CMR',
    'Paraguay': 'PAR', 'Venezuela': 'VEN', 'Chile': 'CHI', 'Peru': 'PER',
    'Bosnia & Herzegovina': 'BIH', 'New Zealand': 'NZL', 'Panama': 'PAN',
    'Jamaica': 'JAM', 'Honduras': 'HON', 'Jordan': 'JOR', 'Haiti': 'HAI',
    'El Salvador': 'SLV', 'Türkiye': 'TUR', 'Turkiye': 'TUR',
}


def load_glicko2_ratings() -> Dict:
    """加载 data/elo_glicko2.json (glicko2_train.py 预生成).

    Returns:
        {
            'generatedAt': str, 'method': str,
            'systemConstant': float, 'homeBonus': float,
            'matchesApplied': int, 'metrics': dict, 'byYear': dict,
            'ratings': {team_name: {'rating': float, 'rd': float, 'volatility': float}}
        }
    """
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "data" / "elo_glicko2.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Glicko-2 评分文件不存在: {path}\n"
            f"运行训练: python scripts/glicko2_train.py"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lookup_glicko2_rating(fifa_code: str) -> Optional[Dict]:
    """按 FIFA 3-letter code 查 Glicko-2 评分.

    Returns:
        {'rating': float, 'rd': float, 'volatility': float} or None
    """
    data = load_glicko2_ratings()
    ratings = data.get("ratings", {})

    # 反向: FIFA code → name
    for name, code in G2_NAME_TO_CODE.items():
        if code == fifa_code:
            if name in ratings:
                return ratings[name]
            # 试 slug
            slug = G2_FIFA_TO_SLUG.get(fifa_code)
            if slug and slug in ratings:
                return ratings[slug]
    return None
