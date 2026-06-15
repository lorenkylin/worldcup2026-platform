"""
M1.2 步骤 2: 4 年回测（913 场真实国际赛 walk-forward）
- 输入: hicruben/results.json (913 场 2023-10 ~ 2026-06)
- 输出: RPS / log-loss / Brier / ECE / Accuracy 5 指标
- 模型: Elo + Dixon-Coles bivariate Poisson
- 评估: walk-forward（每场赛前只看到该场之前的数据）
"""
import json
import math
from datetime import datetime
from collections import defaultdict
from pathlib import Path

RESULTS = r'D:\WorkBuddy\2026FIFA\worldcup2026-platform\data\seed\hicruben\results.json'
OUTPUT = r'D:\WorkBuddy\2026FIFA\worldcup2026-platform\data\seed\hicruben\backtest_metrics.json'

# === Elo 参数（与 Hicruben 一致）===
K_FACTOR = 40  # 国际赛标准 K 因子
HOME_BONUS = 70  # 主场优势
INIT_RATING = 1500

# Dixon-Coles 参数
DC_RHO = -0.13  # ρ 修正

def expected_goals(rating, opponent, home_bonus=0):
    diff = (rating + home_bonus) - opponent
    return max(0.3, min(3.5, 1.35 + diff / 400))

def poisson_pmf(k, lam):
    if lam <= 0:
        return 1 if k == 0 else 0
    p = math.exp(-lam)
    for i in range(1, k+1):
        p *= lam / i
    return p

def dc_tau(a, b, lam, mu, rho):
    if a == 0 and b == 0: return 1 - lam * mu * rho
    if a == 0 and b == 1: return 1 + lam * rho
    if a == 1 and b == 0: return 1 + mu * rho
    if a == 1 and b == 1: return 1 - rho
    return 1

def match_prob(rating_a, rating_b, home_bonus_a=0):
    """Elo + Dixon-Coles 1X2 概率"""
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
        return 1/3, 1/3, 1/3
    return win_a/total, draw/total, win_b/total

def elo_update(rating_a, rating_b, score_a, home_bonus_a=0, k=K_FACTOR):
    """Elo 更新（赛后）"""
    expected_a = 1 / (1 + 10 ** ((rating_b - (rating_a + home_bonus_a)) / 400))
    expected_b = 1 - expected_a
    new_a = rating_a + k * (score_a - expected_a)
    score_b = 1 - score_a
    new_b = rating_b + k * (score_b - expected_b)
    return new_a, new_b

def score_to_1x2(home, away):
    if home > away: return 1, 0, 0
    if home < away: return 0, 0, 1
    return 0, 1, 0

def rps(probs, outcome):
    """Ranked Probability Score (越小越好). probs=[p_home, p_draw, p_away], outcome=[1,0,0]"""
    cum_p = 0; cum_o = 0
    rps_val = 0
    for i in range(3):
        cum_p += probs[i]
        cum_o += outcome[i]
        rps_val += (cum_p - cum_o) ** 2
    return rps_val / 2

def log_loss(probs, outcome, eps=1e-15):
    p_pred = max(eps, min(1-eps, sum(probs[i]*outcome[i] for i in range(3))))
    return -math.log(p_pred)

def brier(probs, outcome):
    return sum((probs[i] - outcome[i]) ** 2 for i in range(3))

def ece(probs_list, outcome_list, n_bins=10):
    """Expected Calibration Error"""
    bins = defaultdict(list)
    for probs, outcome in zip(probs_list, outcome_list):
        pred_max = max(probs)
        idx = probs.index(pred_max)
        bin_idx = min(int(pred_max * n_bins), n_bins - 1)
        bins[bin_idx].append((probs[idx], outcome[idx]))
    ece_val = 0
    total = len(probs_list)
    for bin_idx, samples in bins.items():
        if not samples: continue
        bin_center = (bin_idx + 0.5) / n_bins
        avg_pred = sum(s[0] for s in samples) / len(samples)
        avg_actual = sum(s[1] for s in samples) / len(samples)
        ece_val += (len(samples) / total) * abs(avg_pred - avg_actual)
    return ece_val

def main():
    data = json.loads(Path(RESULTS).read_text(encoding='utf-8'))
    matches = data.get('matches', data) if isinstance(data, dict) else data
    print(f'总比赛: {len(matches)}')
    if matches:
        print(f'首场: {matches[0].get("date", "?")}  末场: {matches[-1].get("date", "?")}')

    # 初始化所有球队 Elo（用 homeName/awayName，因为 t1/t2 不一定存在）
    ratings = defaultdict(lambda: INIT_RATING)

    # 收集所有球队
    all_teams = set()
    for m in matches:
        h = m.get('homeName') or m.get('t1') or m.get('home')
        a = m.get('awayName') or m.get('t2') or m.get('away')
        if h: all_teams.add(h)
        if a: all_teams.add(a)
    print(f'参赛队总数: {len(all_teams)}')

    # 按日期排序
    matches_sorted = sorted(matches, key=lambda m: m.get('date', ''))

    # Walk-forward 回测
    probs_history = []
    outcome_history = []
    burn_in = 150
    evaluated = 0
    correct = 0
    for i, m in enumerate(matches_sorted):
        h = m.get('homeName') or m.get('t1') or m.get('home')
        a = m.get('awayName') or m.get('t2') or m.get('away')
        g1 = m.get('hg', m.get('homeScore', m.get('g1', 0)))
        g2 = m.get('ag', m.get('awayScore', m.get('g2', 0)))
        # 预测（用赛前 Elo）
        r1, r2 = ratings[h], ratings[a]
        p_home, p_draw, p_away = match_prob(r1, r2, home_bonus_a=HOME_BONUS)
        outcome = list(score_to_1x2(g1, g2))

        # 记录（仅评估期）
        if i >= burn_in:
            probs_history.append([p_home, p_draw, p_away])
            outcome_history.append(outcome)
            evaluated += 1
            if max(range(3), key=lambda i: [p_home, p_draw, p_away][i]) == max(range(3), key=lambda i: outcome[i]):
                correct += 1

        # 赛后更新 Elo（不论 burn-in）
        s1 = 1 if g1 > g2 else (0.5 if g1 == g2 else 0)
        new_r1, new_r2 = elo_update(r1, r2, s1, home_bonus_a=HOME_BONUS)
        ratings[h] = new_r1
        ratings[a] = new_r2

    # 计算指标
    rps_vals = [rps(p, o) for p, o in zip(probs_history, outcome_history)]
    log_loss_vals = [log_loss(p, o) for p, o in zip(probs_history, outcome_history)]
    brier_vals = [brier(p, o) for p, o in zip(probs_history, outcome_history)]

    avg_rps = sum(rps_vals) / len(rps_vals)
    avg_log_loss = sum(log_loss_vals) / len(log_loss_vals)
    avg_brier = sum(brier_vals) / len(brier_vals)
    accuracy = correct / evaluated if evaluated > 0 else 0
    ece_val = ece(probs_history, outcome_history)

    print(f'\n========== 4 年回测结果（{evaluated} 场评估，burn-in {burn_in}）==========')
    print(f'  Ranked Probability Score: {avg_rps:.4f}  (Hicruben 参考: 0.175)')
    print(f'  Log-loss:                 {avg_log_loss:.4f}  (Hicruben 参考: 0.89)')
    print(f'  Brier score:              {avg_brier:.4f}  (Hicruben 参考: 0.52)')
    print(f'  Expected Calibration:     {ece_val*100:.2f}%  (Hicruben 参考: 2.3%)')
    print(f'  Accuracy (predicted top): {accuracy*100:.1f}%  (Hicruben 参考: 62%)')

    # 按预测置信度分层（校准表）
    print(f'\n--- 校准表（按预测概率分层）---')
    bins = defaultdict(lambda: [0, 0])  # bin -> [count, correct]
    for probs, outcome in zip(probs_history, outcome_history):
        pred_max = max(probs)
        idx_pred = probs.index(pred_max)
        idx_actual = outcome.index(1) if 1 in outcome else -1
        if idx_pred == idx_actual:
            bins[round(pred_max * 10) / 10][0] += 1
            bins[round(pred_max * 10) / 10][1] += 1
        else:
            bins[round(pred_max * 10) / 10][0] += 1
    print(f'  预测  | 命中率 | 场数')
    for b in sorted(bins.keys()):
        cnt, crr = bins[b]
        rate = crr / cnt if cnt else 0
        print(f'  {b:.0%}    | {rate:.0%}   | {cnt}')

    # 保存结果
    result = {
        'evaluated': evaluated,
        'burn_in': burn_in,
        'total_matches': len(matches_sorted),
        'metrics': {
            'rps': round(avg_rps, 4),
            'log_loss': round(avg_log_loss, 4),
            'brier': round(avg_brier, 4),
            'ece_pct': round(ece_val * 100, 2),
            'accuracy_pct': round(accuracy * 100, 1),
        },
        'parameters': {
            'k_factor': K_FACTOR,
            'home_bonus': HOME_BONUS,
            'dc_rho': DC_RHO,
            'init_rating': INIT_RATING,
        },
        'date_range': [matches_sorted[0].get('date'), matches_sorted[-1].get('date')],
        'note': 'Pure walk-forward, no future data used.',
    }
    Path(OUTPUT).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n✅ 回测结果已存 {OUTPUT}')

if __name__ == '__main__':
    main()
