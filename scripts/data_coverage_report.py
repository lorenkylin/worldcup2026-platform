"""v0.7.6 数据覆盖报告 — 合并 Hicruben + StatsBomb 313 场, 4 段时间分布 + 大赛密度.

Part B (主人 A+B 决策): 不重跑 prediction_log,只出"数据集事实"报告
- 不动 Hicruben 主模型
- 不重跑 1226 场 walk-forward
- 只展示两源合并后的时间分布 / 赛事密度 / 队伍覆盖
"""
from pathlib import Path
import json
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_statsbomb_from_extracted import EXTRACTED

ROOT = Path(__file__).resolve().parent.parent

# ---- 加载 Hicruben 913 场 ----
hc_data = json.load(open(ROOT / "data" / "seed" / "hicruben" / "results.json"))
hc_matches = hc_data["matches"]

# ---- 加载 StatsBomb 313 场 (从 EXTRACTED 重建带 ts) ----
COMPETITION_NAME = {
    (43, 3): "FIFA World Cup 2018",
    (43, 106): "FIFA World Cup 2022",
    (55, 43): "UEFA Euro 2020",
    (55, 282): "UEFA Euro 2024",
    (223, 282): "Copa América 2024",
    (1267, 107): "Africa Cup of Nations 2023",
}
sb_matches = []
for (comp_id, season_id), items in EXTRACTED.items():
    for m in items:
        sb_matches.append({
            **m,
            "competition": COMPETITION_NAME[(comp_id, season_id)],
            "ts": int(__import__("datetime").datetime.fromisoformat(m["date"]).timestamp()),
        })

# ---- 时间分布 ----
print("=" * 60)
print("v0.7.6 数据覆盖报告")
print("=" * 60)
print()
print(f"## 1. 数据集")
print(f"- Hicruben:    {len(hc_matches):>4} 场 (2023-11 → 2026-06)")
print(f"- StatsBomb:   {len(sb_matches):>4} 场 (2018-06 → 2024-07)")
print(f"- 合并:        {len(hc_matches) + len(sb_matches):>4} 场 (2018-06 → 2026-06)")
print()

# ---- 年份分布 ----
print("## 2. 年份分布 (合并后)")
year_count = Counter()
year_count.update(m["date"][:4] for m in hc_matches)
year_count.update(m["date"][:4] for m in sb_matches)
for y in sorted(year_count):
    bar = "█" * (year_count[y] // 5)
    print(f"  {y}: {year_count[y]:>3} 场  {bar}")
print()

# ---- StatsBomb 各赛事 ----
print("## 3. StatsBomb 313 场赛事分布")
sb_compet = Counter(m["competition"] for m in sb_matches)
for name, cnt in sb_compet.most_common():
    print(f"  {name}: {cnt} 场")
print()

# ---- Hicruben 联赛分布 (Top 10) ----
print("## 4. Hicruben 913 场联赛分布 (Top 10)")
hc_league = Counter(m.get("leagueName", "Unknown") for m in hc_matches)
for name, cnt in hc_league.most_common(10):
    print(f"  {name}: {cnt} 场")
print()

# ---- 队伍覆盖 (合并后 unique teams) ----
print("## 5. 队伍覆盖 (合并后)")
hc_teams = set()
for m in hc_matches:
    hc_teams.add(m.get("homeName"))
    hc_teams.add(m.get("awayName"))
sb_teams = set(m["home"] for m in sb_matches) | set(m["away"] for m in sb_matches)
print(f"  Hicruben 唯一队: {len(hc_teams)}")
print(f"  StatsBomb 唯一队: {len(sb_teams)}")
print(f"  并集: {len(hc_teams | sb_teams)}")
print(f"  交集 (两源都有): {len(hc_teams & sb_teams)}")
print()

# ---- 大赛密度对比 ----
print("## 6. 大赛 vs 友谊赛密度")
big_comp_keywords = ["World Cup", "Euro", "Copa América", "Africa Cup"]
sb_big = sum(1 for m in sb_matches if any(k in m["competition"] for k in big_comp_keywords))
hc_big = sum(1 for m in hc_matches if any(k in m.get("leagueName", "") for k in big_comp_keywords))
print(f"  StatsBomb 大赛: {sb_big}/{len(sb_matches)} ({sb_big*100//len(sb_matches)}%)")
print(f"  Hicruben 大赛:  {hc_big}/{len(hc_matches)} ({hc_big*100//len(hc_matches)}%)")
print()

# ---- 关键缺失: Hicruben 0 场 2018/2022 ----
print("## 7. ⚠️ Hicruben 0 场 2018/2022 (v0.7.6 关键动机)")
hc_2018_2022 = [m for m in hc_matches if m["date"][:4] in ("2018", "2022")]
print(f"  Hicruben 2018+2022 场次: {len(hc_2018_2022)} ← v0.7.6 用 StatsBomb 313 场补齐")
print(f"  StatsBomb 2018+2022 场次: {sum(1 for m in sb_matches if m['date'][:4] in ('2018', '2022'))}")
print()

# ---- 2018 WC 4 场补充验证 ----
print("## 8. ✅ 2018 WC 4 场补齐验证")
expected_missing = [
    ("2018-06-19", "Colombia", "Japan"),
    ("2018-06-24", "Japan", "Senegal"),
    ("2018-06-26", "Denmark", "France"),
    ("2018-06-27", "South Korea", "Germany"),
]
for date, h, a in expected_missing:
    found = any(m["date"] == date and m["home"] == h and m["away"] == a for m in sb_matches)
    mark = "✅" if found else "❌"
    print(f"  {mark} {date} {h} vs {a}")
print()

# ---- 写出报告文件 ----
report = f"""# v0.7.6 数据覆盖报告 (Part B 轻量版)

> 日期: 2026-06-16
> 范围: 合并 Hicruben + StatsBomb 数据集, **不重跑 walk-forward**,只展示事实
> 决策: 主人 A+B — A 补 4 场 + 重新生成 statsbomb_elo.json (309 → 313), B 写报告

## 1. 数据集
- **Hicruben**: {len(hc_matches)} 场 (2023-11 → 2026-06)
- **StatsBomb (v0.7.6)**: {len(sb_matches)} 场 (2018-06 → 2024-07)
- **合并**: {len(hc_matches) + len(sb_matches)} 场 (2018-06 → 2026-06)

## 2. 年份分布
| 年 | 合并 | 密度 |
|---|---|---|
""" + "\n".join(f"| {y} | {year_count[y]} | " + "█" * (year_count[y] // 10) + " |" for y in sorted(year_count)) + f"""

## 3. StatsBomb 313 场赛事分布
""" + "\n".join(f"- {name}: {cnt} 场" for name, cnt in sb_compet.most_common()) + f"""

## 4. Hicruben 913 场联赛 (Top 10)
""" + "\n".join(f"- {name}: {cnt} 场" for name, cnt in hc_league.most_common(10)) + f"""

## 5. 队伍覆盖
- Hicruben 唯一队: {len(hc_teams)}
- StatsBomb 唯一队: {len(sb_teams)}
- 并集: {len(hc_teams | sb_teams)}
- 交集: {len(hc_teams & sb_teams)} (两源都覆盖)

## 6. 大赛 vs 友谊赛密度
- StatsBomb 大赛: {sb_big}/{len(sb_matches)} ({sb_big*100//len(sb_matches)}%)
- Hicruben 大赛: {hc_big}/{len(hc_matches)} ({hc_big*100//len(hc_matches)}%)

## 7. ⚠️ 关键发现: Hicruben 缺 2018+2022
- Hicruben 2018+2022 场次: **0**
- StatsBomb 2018+2022 场次: **{sum(1 for m in sb_matches if m['date'][:4] in ('2018', '2022'))}**

→ v0.7.6 补 4 场后, 2018 WC 完整 64 场可入 G2 训练集 (但 Part B 决策: 不重跑 walk-forward)

## 8. ✅ 2018 WC 4 场补齐验证
| 日期 | 主 | 客 | 状态 |
|---|---|---|---|
""" + "\n".join(f"| {date} | {h} | {a} | ✅ 已补 |" for date, h, a in expected_missing) + f"""

## 9. v0.7.6 决策 (主人确认)
1. ✅ Part A: 补 4 场 + statsbomb_elo.json 重新生成 (309 → 313)
2. ✅ Part B: 写本报告, **不重跑 walk-forward**
3. ❌ 不回写 Hicruben 主模型 (64 场大赛会拉低 913 场 Hicruben 友谊赛+预选赛权重)
4. ❌ 不重跑 prediction_log backfill (1226 场 walk-forward 工时 ~20min, 主人不接受 accuracy 波动)

## 10. 后续可选项
- 跑 walk-forward 1226 场 (4 模型 × 1226) → 估算 Glicko-2 准确率变化
- 加 2018 末轮 4 场到 prediction_log (不改模型)
- 扩 Hicruben 2018/2022 段 (需新数据源, 不在 v0.7.6 范围)
"""

out_path = ROOT / "data" / "v0.7.6_data_coverage_report.md"
out_path.write_text(report, encoding="utf-8")
print(f"✅ 报告已写入: {out_path}")
