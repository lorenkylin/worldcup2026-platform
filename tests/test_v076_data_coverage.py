"""v0.7.6 数据覆盖测试: 4 场补齐 + 313 场 statsbomb_elo.json 验证."""
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SB_JSON = ROOT / "data" / "seed" / "statsbomb" / "statsbomb_elo.json"

# 主人 A+B 决策要求验证
EXPECTED_NEW_4 = [
    ("2018-06-19", "Colombia", 1, "Japan", 2),
    ("2018-06-24", "Japan", 2, "Senegal", 2),
    ("2018-06-26", "Denmark", 0, "France", 0),
    ("2018-06-27", "South Korea", 2, "Germany", 0),
]


def test_2018_wc_4_missing_filled():
    """2018 WC 4 场小组赛末轮冷门/强队对话已补齐."""
    from scripts.build_statsbomb_from_extracted import EXTRACTED
    w18 = EXTRACTED[(43, 3)]
    assert len(w18) == 64, f"2018 WC 应有 64 场, 实际 {len(w18)} 场"
    for date, h, hg, a, ag in EXPECTED_NEW_4:
        found = any(
            m["date"] == date and m["home"] == h and m["away"] == a
            and m["hg"] == hg and m["ag"] == ag
            for m in w18
        )
        assert found, f"❌ 缺 {date} {h} {hg}-{ag} {a}"


def test_statsbomb_elo_json_has_313_matches():
    """statsbomb_elo.json 重新生成后 matchesApplied = 313 (v0.7.6 之前 309)."""
    assert SB_JSON.exists(), f"❌ 缺 {SB_JSON}"
    data = json.load(open(SB_JSON))
    assert data["matchesApplied"] == 313, f"❌ matchesApplied={data['matchesApplied']}, 期望 313"
    # v0.7.6 必含 6 个赛事
    comp_str = ", ".join(data["sourceCompetitions"])
    assert "FIFA World Cup 2018" in comp_str
    assert "FIFA World Cup 2022" in comp_str


def test_hicruben_zero_2018_2022_motivates_v076():
    """Hicruben 完全无 2018/2022 数据, 这是 v0.7.6 关键动机."""
    hc = json.load(open(ROOT / "data" / "seed" / "hicruben" / "results.json"))
    matches_2018_2022 = [m for m in hc["matches"] if m["date"][:4] in ("2018", "2022")]
    assert len(matches_2018_2022) == 0, f"❌ Hicruben 2018/2022 场次: {len(matches_2018_2022)}, 期望 0"


def test_data_coverage_report_markdown_written():
    """data_coverage_report 脚本产出的 markdown 文件已写入."""
    report = ROOT / "data" / "v0.7.6_data_coverage_report.md"
    assert report.exists(), f"❌ 缺 {report}"
    text = report.read_text(encoding="utf-8")
    assert "FIFA World Cup 2018: 64 场" in text
    assert "1226 场" in text  # 合并后总场次
    assert "2018-06-19 | Colombia | Japan" in text  # 4 场补齐列在表里
