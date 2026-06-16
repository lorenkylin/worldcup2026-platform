"""历史 2018+2022 prediction_log 回填脚本 (v0.6.0).

逻辑:
  1. 加载 Hicruben 913 场 (含 2018+2022 历史 128 场)
  2. walk-forward 模式: 对每场 i, 用 i 之前所有数据训练 Elo + Glicko-2
  3. 预测 i, 写 prediction_log (correct 立即可填)
  4. 输出 accuracy/RPS/Brier/LogLoss 对比表

输出:
  - data/prediction_log_backfill.jsonl
  - data/backfill_report.md
"""
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.elo import predict_match_enhanced, load_elo_ratings
from app.services import glicko2 as g2
from app.services.elo import HOME_BONUS

# 加载 Hicruben 913 场
DATA = json.load(open(ROOT / "data" / "seed" / "hicruben" / "results.json", encoding="utf-8"))
ALL_MATCHES = sorted(DATA["matches"], key=lambda m: m["ts"])

# FIFA code 转换 (Hicruben name → FIFA code)
NAME_TO_FIFA = {
    "Mexico": "MEX", "South Africa": "RSA", "South Korea": "KOR", "Czech Republic": "CZE",
    "United States": "USA", "Canada": "CAN", "Brazil": "BRA", "Morocco": "MAR",
    "Argentina": "ARG", "France": "FRA", "Spain": "ESP", "England": "ENG",
    "Germany": "GER", "Italy": "ITA", "Portugal": "POR", "Netherlands": "NED",
    "Belgium": "BEL", "Croatia": "CRO", "Uruguay": "URU", "Colombia": "COL",
    "Japan": "JPN", "Senegal": "SEN", "Denmark": "DEN", "Ecuador": "ECU",
    "Switzerland": "SUI", "Australia": "AUS", "Iran": "IRN", "Poland": "POL",
    "Serbia": "SRB", "Wales": "WAL", "Ghana": "GHA", "Tunisia": "TUN",
    "Ivory Coast": "CIV", "Nigeria": "NGA", "Saudi Arabia": "KSA", "Qatar": "QAT",
    "Egypt": "EGY", "Algeria": "ALG", "Scotland": "SCO", "Cameroon": "CMR",
    "Paraguay": "PAR", "Venezuela": "VEN", "Chile": "CHI", "Peru": "PER",
    "Bosnia & Herzegovina": "BIH", "New Zealand": "NZL", "Panama": "PAN",
    "Jamaica": "JAM", "Honduras": "HON", "Jordan": "JOR", "Haiti": "HAI",
    "El Salvador": "SLV", "Türkiye": "TUR", "Turkiye": "TUR", "Bolivia": "BOL",
    "Luxembourg": "LUX", "Romania": "ROU", "Slovakia": "SVK", "Hungary": "HUN",
    "Sweden": "SWE", "Norway": "NOR", "Finland": "FIN", "Iceland": "ISL",
    "Republic of Ireland": "IRL", "Ireland": "IRL", "Greece": "GRE",
    "Ukraine": "UKR", "Kosovo": "KOS", "Montenegro": "MNE", "North Macedonia": "MKD",
    "Albania": "ALB", "Bulgaria": "BUL", "Moldova": "MDA", "Latvia": "LVA",
    "Lithuania": "LTU", "Estonia": "EST", "Cyprus": "CYP", "Malta": "MLT",
    "San Marino": "SMR", "Liechtenstein": "LIE", "Andorra": "AND", "Gibraltar": "GIB",
    "Belarus": "BLR", "Faroe Islands": "FRO", "Northern Ireland": "NIR",
    "Israel": "ISR", "Azerbaijan": "AZE", "Georgia": "GEO", "Armenia": "ARM",
    "Kazakhstan": "KAZ", "Uzbekistan": "UZB", "Russia": "RUS", "Turkey": "TUR",
}


def name_to_code(name: str) -> str:
    return NAME_TO_FIFA.get(name, name[:3].upper())


def elo_walk_forward(matches, home_bonus=HOME_BONUS, k=60):
    """对每场 i, 用 i 之前所有数据预测, 然后 Elo 更新.

    Returns:
        List of {match_id, date, home, away, ph, pd, pa, actual, correct, model}
    """
    state = defaultdict(lambda: 1500.0)
    results = []
    for m in matches:
        home = name_to_code(m["homeName"])
        away = name_to_code(m["awayName"])
        rh, ra = state[home], state[away]

        # 1. 预测 (M1 Elo + Dixon-Coles)
        # 简化: 用 logistic 期望 + 经验平局率
        exp_a = 1 / (1 + 10 ** ((ra - (rh + home_bonus)) / 400))
        exp_b = 1 - exp_a
        diff = abs(rh + home_bonus - ra)
        draw = max(0.10, 0.26 - diff * 0.0005)
        ph = exp_a * (1 - draw)
        pa = exp_b * (1 - draw)

        # 2. 实际
        hg, ag = m["hg"], m["ag"]
        actual = "home" if hg > ag else ("away" if ag > hg else "draw")
        actual_letter = {"home": "H", "draw": "D", "away": "A"}[actual]
        pred_letter = "H" if ph >= pa and ph >= draw else ("D" if draw >= pa else "A")
        correct = int(pred_letter == actual_letter)

        results.append({
            "match_id": m["id"],
            "date": m["date"],
            "home_team": home,
            "away_team": away,
            "ph": round(ph, 4),
            "pd": round(draw, 4),
            "pa": round(pa, 4),
            "actual_outcome": actual,
            "predicted_outcome": pred_letter,
            "correct": correct,
            "model": "v1_elo_walkforward",
        })

        # 3. 更新 Elo
        score = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        expected = exp_a
        state[home] = rh + k * (score - expected)
        state[away] = ra + k * ((1 - score) - exp_b)

    return results


def glicko2_walk_forward(matches, tau=0.5, home_bonus=HOME_BONUS):
    """Glicko-2 walk-forward (复用 glicko2_train 的 init_state)."""
    from scripts.glicko2_train import init_state
    state = init_state()
    by_day = defaultdict(list)
    for m in matches:
        by_day[m["date"]].append(m)

    results = []
    for day in sorted(by_day.keys()):
        day_matches = by_day[day]
        day_pred = []
        for m in day_matches:
            home = m["homeName"]
            away = m["awayName"]
            if home not in state or away not in state:
                continue
            rh, rdh, _ = state[home]
            ra, rda, _ = state[away]
            pred = g2.predict_outcome(rh, rdh, ra, rda, home_bonus=home_bonus)
            hg, ag = m["hg"], m["ag"]
            actual = "home" if hg > ag else ("away" if ag > hg else "draw")
            actual_letter = {"home": "H", "draw": "D", "away": "A"}[actual]
            pred_letter = "H" if pred["win_a"] >= pred["draw"] and pred["win_a"] >= pred["win_b"] else ("D" if pred["draw"] >= pred["win_b"] else "A")
            day_pred.append({
                "match_id": m["id"],
                "date": day,
                "home_team": name_to_code(home),
                "away_team": name_to_code(away),
                "ph": round(pred["win_a"], 4),
                "pd": round(pred["draw"], 4),
                "pa": round(pred["win_b"], 4),
                "actual_outcome": actual,
                "predicted_outcome": pred_letter,
                "correct": int(pred_letter == actual_letter),
                "model": "v3_glicko2_walkforward",
            })

        # 批量更新
        to = defaultdict(list)
        for m in day_matches:
            home, away = m["homeName"], m["awayName"]
            if home not in state or away not in state:
                continue
            rh, rdh, sh = state[home]
            ra, rda, sa = state[away]
            hg, ag = m["hg"], m["ag"]
            sc = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
            to[home].append((ra, rda, sc))
            to[away].append((rh, rdh, 1.0 - sc))
        for t, op in to.items():
            r, rd, s = state[t]
            state[t] = g2.rate_period(r, rd, s, op, tau=tau)

        results.extend(day_pred)
    return results


def compute_metrics(results):
    """accuracy/RPS/Brier/LogLoss."""
    n = len(results)
    if n == 0:
        return {}
    correct = sum(r["correct"] for r in results)
    accuracy = correct / n
    rps_sum = brier_sum = logloss_sum = 0.0
    for r in results:
        ph, pd, pa = r["ph"], r["pd"], r["pa"]
        if r["actual_outcome"] == "home":
            yh, yd, ya = 1, 0, 0
        elif r["actual_outcome"] == "draw":
            yh, yd, ya = 0, 1, 0
        else:
            yh, yd, ya = 0, 0, 1
        rps_sum += 0.5 * ((ph - yh) ** 2 + (ph + pd - yh - yd) ** 2)
        brier_sum += (ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2
        p_actual = [ph, pd, pa][[yh, yd, ya].index(1)]
        logloss_sum += -math.log(max(p_actual, 1e-15))
    return {
        "n": n,
        "accuracy": round(accuracy, 4),
        "rps": round(rps_sum / n, 4),
        "brier": round(brier_sum / n, 4),
        "log_loss": round(logloss_sum / n, 4),
    }


def metrics_by_year(results):
    by = defaultdict(list)
    for r in results:
        by[r["date"][:4]].append(r["correct"])
    return {y: {"n": len(v), "accuracy": round(sum(v) / len(v), 4)} for y, v in sorted(by.items())}


def main():
    print("=" * 70)
    print("v0.6.0 历史回填 - Elo M1 + Glicko-2 walk-forward")
    print(f"输入: Hicruben {len(ALL_MATCHES)} 场 (2023-11 ~ 2026-06)")
    print("=" * 70)

    print("\n--- 1. Elo M1 walk-forward ---")
    elo_results = elo_walk_forward(ALL_MATCHES)
    elo_m = compute_metrics(elo_results)
    elo_by = metrics_by_year(elo_results)
    print(f"整体: {elo_m}")

    print("\n--- 2. Glicko-2 walk-forward ---")
    g2_results = glicko2_walk_forward(ALL_MATCHES)
    g2_m = compute_metrics(g2_results)
    g2_by = metrics_by_year(g2_results)
    print(f"整体: {g2_m}")

    # 保存
    out_path = ROOT / "data" / "prediction_log_backfill.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in elo_results + g2_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n✓ 保存到 {out_path} ({len(elo_results) + len(g2_results)} 行)")

    # 生成 markdown 报告
    report = []
    report.append("# v0.6.0 预测模型历史回填报告\n")
    report.append(f"生成时间: {datetime.utcnow().isoformat()}Z\n")
    report.append(f"输入: Hicruben {len(ALL_MATCHES)} 场国际赛 (2023-11 ~ 2026-06)\n")
    report.append(f"模式: walk-forward (用 i 之前所有数据预测 i)\n\n")

    report.append("## 1. 整体对比\n\n")
    report.append("| 模型 | n | Accuracy | RPS | Brier | LogLoss |\n")
    report.append("|---|---|---|---|---|---|\n")
    report.append(f"| Elo M1 | {elo_m['n']} | {elo_m['accuracy']:.4f} | {elo_m['rps']:.4f} | {elo_m['brier']:.4f} | {elo_m['log_loss']:.4f} |\n")
    report.append(f"| Glicko-2 | {g2_m['n']} | {g2_m['accuracy']:.4f} | {g2_m['rps']:.4f} | {g2_m['brier']:.4f} | {g2_m['log_loss']:.4f} |\n")

    report.append("\n## 2. 按年对比\n\n")
    report.append("| 年 | n | Elo Acc | Glicko-2 Acc | Δ |\n")
    report.append("|---|---|---|---|---|\n")
    for y in sorted(set(elo_by) | set(g2_by)):
        e = elo_by.get(y, {"n": 0, "accuracy": 0})
        g = g2_by.get(y, {"n": 0, "accuracy": 0})
        delta = g["accuracy"] - e["accuracy"]
        report.append(f"| {y} | {e['n']} | {e['accuracy']:.4f} | {g['accuracy']:.4f} | {delta:+.4f} |\n")

    report.append("\n## 3. 偏差分析 (Top 10 Glicko-2 错得最离谱)\n\n")
    # Glicko-2 错误预测
    wrong = [r for r in g2_results if r["correct"] == 0]
    wrong.sort(key=lambda r: -(max(r["ph"], r["pd"], r["pa"]) - {"home": r["ph"], "draw": r["pd"], "away": r["pa"]}[r["actual_outcome"]]))
    report.append("| Date | Match | Predicted | Actual | Confidence | Actual P | Surprise |\n")
    report.append("|---|---|---|---|---|---|---|\n")
    for r in wrong[:10]:
        max_p = max(r["ph"], r["pd"], r["pa"])
        actual_p = {"home": r["ph"], "draw": r["pd"], "away": r["pa"]}[r["actual_outcome"]]
        surprise = max_p - actual_p
        report.append(f"| {r['date']} | {r['away_team']} @ {r['home_team']} | {r['predicted_outcome']} | {r['actual_outcome']} | {max_p:.3f} | {actual_p:.3f} | {surprise:.3f} |\n")

    report.append("\n## 4. 结论\n\n")
    delta = g2_m["accuracy"] - elo_m["accuracy"]
    report.append(f"- Glicko-2 vs Elo M1 准确率: **{delta:+.4f}** ({(delta*100):+.2f} pp)\n")
    report.append(f"- RPS 提升: {elo_m['rps'] - g2_m['rps']:+.4f} ({(elo_m['rps']-g2_m['rps'])/elo_m['rps']*100:+.1f}%)\n")
    report.append(f"- Brier 提升: {elo_m['brier'] - g2_m['brier']:+.4f} ({(elo_m['brier']-g2_m['brier'])/elo_m['brier']*100:+.1f}%)\n\n")
    report.append("**已完赛复盘建议**: 优先看 Glicko-2 的 '偏差分析' 表格, 找出 5-10 场系统性的错误模式 (如对某联赛低估客队), 优化 form/h2h 调整公式。\n")

    report_path = ROOT / "data" / "backfill_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(report)
    print(f"✓ 报告保存到 {report_path}")

    return {"elo": elo_m, "glicko2": g2_m}


if __name__ == "__main__":
    main()
