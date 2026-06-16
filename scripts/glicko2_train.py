"""Glicko-2 训练脚本 - 用 Hicruben 913 场 walk-forward 训练.

输入: data/seed/hicruben/results.json (913 场, 2023-11 ~ 2026-06)
输出:
  - data/elo_glicko2.json (最终 rating 字典)
  - data/glicko2_history.jsonl (每场后的状态)
  - 控制台: 准确率/RPS/Brier/LogLoss
"""
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# 让脚本可以从项目根目录导入
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import glicko2 as g2

# 主场优势 (Elo 分数) — 跟 elo.py 一致
HOME_BONUS = 70.0

# 比赛周期 (1 天 = 1 rating period)
PERIOD_DAYS = 1


def load_matches() -> List[dict]:
    """加载 Hicruben 913 场数据."""
    path = ROOT / "data" / "seed" / "hicruben" / "results.json"
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d["matches"]


def init_state() -> Dict[str, Tuple[float, float, float]]:
    """初始化所有队: 优先用 Hicruben calibrated rating (RD=80, 已校准), 其余用 1500±200 (冷启动).

    Returns:
        dict: team_name -> (rating, RD, volatility)
    """
    cal_path = ROOT / "data" / "seed" / "hicruben" / "elo-calibrated.json"
    with open(cal_path, encoding="utf-8") as f:
        cal = json.load(f)
    calibrated = cal["ratings"]  # kebab-case slug -> rating

    # 反向: kebab-case -> Team.name (用于匹配 matches 里的 homeName/awayName)
    # Hicruben 用 kebab-slug,我们用 "name" 字段
    # 创建两个 lookup: 全名 → slug, slug → rating
    slug_to_rating = calibrated
    # 简化: 把 "name" 当 key 试,失败再试 slugified
    state = {}

    # 收集 matches 里的所有 team 名字
    matches = load_matches()
    team_names = set()
    for m in matches:
        team_names.add(m["homeName"])
        team_names.add(m["awayName"])

    # 简单映射: name -> rating
    def name_to_rating(name: str):
        # 直接匹配 (Hicruben 有些是 "USA", "Mexico" 等)
        for k, v in slug_to_rating.items():
            if k.replace("-", " ").lower() == name.lower():
                return v
            if k == name.lower().replace(" ", "-"):
                return v
            if name.lower() in k or k in name.lower():
                return v
        return None

    matched = 0
    for name in team_names:
        r = name_to_rating(name)
        if r is not None:
            state[name] = (float(r), 80.0, g2.DEFAULT_VOLATILITY)  # 已校准
            matched += 1
        else:
            state[name] = (g2.DEFAULT_RATING, 200.0, g2.DEFAULT_VOLATILITY)  # 冷启动
    print(f"  预热: {matched}/{len(team_names)} 队用 Hicruben 校准, 其余冷启动")
    return state


def walk_forward_train(
    matches: List[dict],
    home_bonus: float = HOME_BONUS,
    batch_by_day: bool = True,
) -> Tuple[Dict, List[dict]]:
    """Walk-forward 训练: 对每场 i, 用 i 之前所有数据预测, 然后更新.

    batch_by_day: 同一天的比赛用 Glicko-2 spec Section 6 的批量更新 (更符合算法原意)
    """
    # 按日期排序
    matches = sorted(matches, key=lambda m: m["ts"])
    print(f"  初始化 {len(matches)} 场比赛的初始状态...")
    state = init_state()
    history = []

    # 按 day 分组 (同一 day 内所有比赛一起更新)
    from collections import defaultdict
    from datetime import datetime as _dt
    by_day = defaultdict(list)
    for m in matches:
        day = m["date"]  # YYYY-MM-DD
        by_day[day].append(m)

    sorted_days = sorted(by_day.keys())

    for day in sorted_days:
        day_matches = by_day[day]

        # Phase 1: 用现有 state 预测每场
        day_history = []
        day_updates = []  # (team, [(opp_rating, opp_rd, score)])
        for m in day_matches:
            home = m["homeName"]
            away = m["awayName"]
            hg, ag = m["hg"], m["ag"]

            rh, rdh, sh = state[home]
            ra, rda, sa = state[away]
            pred = g2.predict_outcome(rh, rdh, ra, rda, home_bonus=home_bonus)
            p_h, p_d, p_a = pred["win_a"], pred["draw"], pred["win_b"]
            pred_outcome = "H" if p_h >= p_d and p_h >= p_a else ("D" if p_d >= p_a else "A")
            actual_outcome = "home" if hg > ag else ("away" if ag > hg else "draw")

            day_history.append({
                "match_id": m["id"],
                "date": m["date"],
                "home": home,
                "away": away,
                "home_rating": round(rh, 1),
                "home_rd": round(rdh, 1),
                "away_rating": round(ra, 1),
                "away_rd": round(rda, 1),
                "pred_home": pred["win_a"],
                "pred_draw": pred["draw"],
                "pred_away": pred["win_b"],
                "uncertainty": pred["uncertainty"],
                "actual_home_score": hg,
                "actual_away_score": ag,
                "actual_outcome": actual_outcome,
                "predicted_outcome": pred_outcome,
                "correct": (pred_outcome == actual_outcome[0].upper()),
            })

            score_home = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
            day_updates.append((home, away, rh, rdh, sh, ra, rda, sa, score_home))

        # Phase 2: 批量更新 (用 Phase 1 时的 rating, 避免污染)
        if batch_by_day:
            # 收集每队当天的对手
            team_opps = defaultdict(list)
            for home, away, rh, rdh, sh, ra, rda, sa, sc in day_updates:
                team_opps[home].append((ra, rda, sc))  # home vs away
                team_opps[away].append((rh, rdh, 1.0 - sc))  # away vs home

            for team, opps in team_opps.items():
                r, rd, s = state[team]
                new_r, new_rd, new_s = g2.rate_period(r, rd, s, opps)
                state[team] = (new_r, new_rd, new_s)
        else:
            # 逐场更新
            for home, away, rh, rdh, sh, ra, rda, sa, sc in day_updates:
                new_rh, new_rdh, new_sh = g2.rate_1vs1(rh, rdh, sh, ra, rda, sc)
                new_ra, new_rda, new_sa = g2.rate_1vs1(ra, rda, sa, rh, rdh, 1.0 - sc)
                state[home] = (new_rh, new_rdh, new_sh)
                state[away] = (new_ra, new_rda, new_sa)

        history.extend(day_history)

    final_ratings = {
        team: {"rating": round(r, 1), "rd": round(rd, 1), "volatility": round(s, 4)}
        for team, (r, rd, s) in state.items()
    }
    return final_ratings, history


def compute_metrics(history: List[dict]) -> dict:
    """计算整体准确率 + RPS + Brier + LogLoss."""
    if not history:
        return {}

    n = len(history)
    correct = sum(1 for h in history if h["correct"])
    accuracy = correct / n

    # RPS (Ranked Probability Score) for 1X2
    rps_sum = 0.0
    brier_sum = 0.0
    logloss_sum = 0.0
    eps = 1e-15

    for h in history:
        ph, pd, pa = h["pred_home"], h["pred_draw"], h["pred_away"]
        if h["actual_outcome"] == "home":
            yh, yd, ya = 1, 0, 0
        elif h["actual_outcome"] == "draw":
            yh, yd, ya = 0, 1, 0
        else:
            yh, yd, ya = 0, 0, 1
        # RPS = (1/2) · [(p_h - y_h)² + (p_h + p_d - y_h - y_d)²]
        rps_sum += 0.5 * (
            (ph - yh) ** 2 +
            (ph + pd - yh - yd) ** 2
        )
        # Brier (3-class)
        brier_sum += (ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2
        # LogLoss
        p_actual = [ph, pd, pa][[yh, yd, ya].index(1)]
        logloss_sum += -math.log(max(p_actual, eps))

    return {
        "n_matches": n,
        "accuracy": round(accuracy, 4),
        "rps": round(rps_sum / n, 4),
        "brier": round(brier_sum / n, 4),
        "log_loss": round(logloss_sum / n, 4),
    }


def metrics_by_year(history: List[dict]) -> dict:
    """按年份分组准确率."""
    by_year = defaultdict(list)
    for h in history:
        y = h["date"][:4]
        by_year[y].append(h["correct"])
    return {y: {"n": len(v), "accuracy": round(sum(v) / len(v), 4)} for y, v in sorted(by_year.items())}


def metrics_by_year_month(history: List[dict]) -> dict:
    """按年月分组的滚动准确率 (报告用)."""
    by_ym = defaultdict(list)
    for h in history:
        ym = h["date"][:7]
        by_ym[ym].append(h["correct"])
    return {ym: {"n": len(v), "accuracy": round(sum(v) / len(v), 4)} for ym, v in sorted(by_ym.items())}


def main():
    print("=" * 70)
    print("Glicko-2 训练 - Hicruben 913 场 walk-forward")
    print("=" * 70)

    matches = load_matches()
    print(f"\n加载 {len(matches)} 场, {len(set(m['homeName'] for m in matches) | set(m['awayName'] for m in matches))} 队")

    final_ratings, history = walk_forward_train(matches)

    metrics = compute_metrics(history)
    by_year = metrics_by_year(history)
    by_ym = metrics_by_year_month(history)

    print("\n=== 整体指标 ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    print("\n=== 按年 ===")
    for y, m in by_year.items():
        print(f"  {y}: n={m['n']:4d}  acc={m['accuracy']:.3f}")

    print("\n=== 按月 (近 12 月) ===")
    for ym in sorted(by_ym.keys())[-12:]:
        m = by_ym[ym]
        print(f"  {ym}: n={m['n']:3d}  acc={m['accuracy']:.3f}")

    # 找出 TOP 10 队
    print("\n=== TOP 10 队 (按 rating) ===")
    top10 = sorted(final_ratings.items(), key=lambda x: x[1]["rating"], reverse=True)[:10]
    for i, (t, r) in enumerate(top10, 1):
        print(f"  {i:2d}. {t:30s} rating={r['rating']:6.1f}  RD={r['rd']:5.1f}  vol={r['volatility']:.4f}")

    # 找出 BOTTOM 5 队
    print("\n=== BOTTOM 5 队 ===")
    bot5 = sorted(final_ratings.items(), key=lambda x: x[1]["rating"])[:5]
    for i, (t, r) in enumerate(bot5, 1):
        print(f"  {t:30s} rating={r['rating']:6.1f}  RD={r['rd']:5.1f}  vol={r['volatility']:.4f}")

    # 保存
    ratings_path = ROOT / "data" / "elo_glicko2.json"
    with open(ratings_path, "w", encoding="utf-8") as f:
        json.dump({
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "method": "Glicko-2 walk-forward on Hicruben 913 matches",
            "systemConstant": g2.DEFAULT_TAU,
            "homeBonus": HOME_BONUS,
            "matchesApplied": len(matches),
            "metrics": metrics,
            "byYear": by_year,
            "ratings": final_ratings,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 评分保存到 {ratings_path}")

    history_path = ROOT / "data" / "glicko2_history.jsonl"
    with open(history_path, "w", encoding="utf-8") as f:
        for h in history:
            f.write(json.dumps(h, ensure_ascii=False) + "\n")
    print(f"✓ 训练历史保存到 {history_path} ({len(history)} 行)")

    return metrics


if __name__ == "__main__":
    main()
