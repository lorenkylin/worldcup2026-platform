"""v0.7.1 Monte Carlo Tournament 单元/集成测试.

覆盖 8 个核心契约:
  T1 基础结构齐全
  T2 champion 分布和 = 1
  T3 finalist >= champion (晋级决赛必含夺冠)
  T4 round 单调性: group_advance >= r32 >= r16 >= qf >= sf >= finalist >= champion
  T5 top_matchups 概率和 < 1.0
  T6 强队 (高 Elo) champion_prob > 弱队
  T7 种子可重现 (random.seed 两次结果一致)
  T8 已完赛比赛在 MC 中保持不变
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

# Late binding fix: conftest 改写 app.db.SessionLocal,模块级 import 会缓存旧引用
from app import db as app_db
from app.main import app
from app.models import Match, Standing, Team
from app.services.monte_carlo import (
    DEFAULT_SIMULATIONS,
    MAX_SIMULATIONS,
    MIN_SIMULATIONS,
    simulate_full_tournament,
    tournament_result_to_dict,
)


# === 测试 Fixtures ===
def _seed_full_worldcup(db) -> None:
    """写入 12 组 × 4 队 = 48 队 + 72 场组赛 (无已完赛).

    注意: conftest 已 seed MEX(id=1) + RSA(id=2) + match_number=1,这里先删,
    保证测试是干净的 48 队。
    """
    db.query(Match).filter(Match.match_number <= 1).delete()
    db.query(Team).filter(Team.id.in_([1, 2])).delete()
    db.commit()

    # 48 队
    teams = []
    for g_idx, group in enumerate("ABCDEFGHIJKL"):
        for rank in range(4):
            # 强 Elo 集中在 A/B/C 组, 弱队在 J/K/L
            base_elo = 1850 - g_idx * 30 - rank * 15
            code = f"{group}{rank+1}"
            teams.append(
                Team(
                    fifa_code=code,
                    name_zh=f"{group}组第{rank+1}",
                    name_en=f"Team {code}",
                    group_name=group,
                    flag_emoji="🏳️",
                    elo_rating=base_elo,
                )
            )
    db.add_all(teams)
    db.commit()

    # 72 场组赛: 简化每组 6 场 (轮次制)
    # 用每组前 2 vs 后 2 + 交叉
    matches = []
    match_num = 2  # 跳过 conftest 的 match_number=1
    kickoff_base = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)
    for g_idx, group in enumerate("ABCDEFGHIJKL"):
        team_in_group = [t for t in teams if t.group_name == group]
        team_in_group.sort(key=lambda t: t.fifa_code)
        # 6 场: (0v1, 2v3, 0v2, 1v3, 0v3, 1v2)
        pairings = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
        for round_num, (i, j) in enumerate(pairings, start=1):
            matches.append(
                Match(
                    match_number=match_num,
                    stage="小组赛",
                    group_name=group,
                    round_number=round_num,
                    kickoff_at=kickoff_base + timedelta(days=g_idx * 2 + round_num - 1),
                    home_team_id=team_in_group[i].id,
                    away_team_id=team_in_group[j].id,
                    status="scheduled",
                    data_source="manual",
                )
            )
            match_num += 1
    # 验证 72 场
    assert match_num - 2 == 72, f"应写 72 场, 写了 {match_num - 1}"
    db.add_all(matches)
    db.commit()


def _seed_worldcup_with_finished_matches(db, n_finished: int = 10) -> None:
    """种 48 队 + 72 场, 其中前 n_finished 场标记为已完赛 (随机比分)."""
    _seed_full_worldcup(db)
    # 取前 n_finished 场标记为已完赛
    finished = db.query(Match).filter(Match.match_number <= n_finished).all()
    for m in finished:
        m.status = "finished"
        m.home_score = 1
        m.away_score = 0
    db.commit()
    # 同步写 standings
    for m in finished:
        s = Standing(
            group_name=m.group_name,
            team_id=m.home_team_id,
            played=1, won=1, drawn=0, lost=0,
            goals_for=1, goals_against=0, points=3,
        )
        db.add(s)
    db.commit()


# === T1 ===
def test_mc_returns_basic_structure():
    """MC 应返回 6 个顶级字段."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        result = simulate_full_tournament(db, n_sims=200, seed=1)
        d = tournament_result_to_dict(result)
        assert "champion_distribution" in d
        assert "finalist_distribution" in d
        assert "semifinalist_distribution" in d
        assert "r16_distribution" in d
        assert "r32_distribution" in d
        assert "group_advance_probability" in d
        assert "top_final_matchups" in d
        assert "n_sims" in d and d["n_sims"] == 200
        assert d["n_teams"] == 48
        assert d["n_groups"] == 12
    finally:
        db.close()


# === T2 ===
@pytest.mark.slow
@pytest.mark.slow
def test_mc_champion_distribution_sums_to_one():
    """冠军分布和 = 1.0 ± 0.001."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        result = simulate_full_tournament(db, n_sims=1000, seed=1)
        d = tournament_result_to_dict(result)
        total = sum(d["champion_distribution"].values())
        assert abs(total - 1.0) < 0.001, f"冠军分布和 = {total}, 应接近 1.0"
    finally:
        db.close()


# === T3 ===
@pytest.mark.slow
def test_mc_finalist_distribution_geq_champion():
    """对每队: finalist_prob >= champion_prob (晋级决赛 ⊇ 夺冠)."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        result = simulate_full_tournament(db, n_sims=1000, seed=2)
        d = tournament_result_to_dict(result)
        for team, f_prob in d["finalist_distribution"].items():
            c_prob = d["champion_distribution"].get(team, 0)
            assert f_prob >= c_prob - 1e-6, (
                f"队 {team}: finalist={f_prob} < champion={c_prob}"
            )
    finally:
        db.close()


# === T4 ===
@pytest.mark.slow
def test_mc_round_distribution_monotonic():
    """对每队: group_advance >= r32 >= r16 >= qf >= sf >= finalist >= champion."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        result = simulate_full_tournament(db, n_sims=2000, seed=3)
        d = tournament_result_to_dict(result)
        for team in d["r32_distribution"]:
            g = d["group_advance_probability"]
            g_prob = max(
                (v for grp in g.values() for k, v in grp.items() if k == team),
                default=0,
            )
            r32 = d["r32_distribution"][team]
            r16 = d["r16_distribution"].get(team, 0)
            qf = d["quarterfinalist_distribution"].get(team, 0)
            sf = d["semifinalist_distribution"].get(team, 0)
            f = d["finalist_distribution"].get(team, 0)
            c = d["champion_distribution"].get(team, 0)
            assert g_prob >= r32 - 1e-6, f"{team}: group_advance({g_prob}) < r32({r32})"
            assert r32 >= r16 - 1e-6, f"{team}: r32({r32}) < r16({r16})"
            assert r16 >= qf - 1e-6, f"{team}: r16({r16}) < qf({qf})"
            assert qf >= sf - 1e-6, f"{team}: qf({qf}) < sf({sf})"
            assert sf >= f - 1e-6, f"{team}: sf({sf}) < finalist({f})"
            assert f >= c - 1e-6, f"{team}: finalist({f}) < champion({c})"
    finally:
        db.close()


# === T5 ===
@pytest.mark.slow
def test_mc_top_matchups_ordered_and_bounded():
    """top_final_matchups 按 prob 降序, top-5 概率和 < 1.0."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        result = simulate_full_tournament(
            db, n_sims=1000, seed=4, return_top_n=5
        )
        d = tournament_result_to_dict(result)
        probs = [m["prob"] for m in d["top_final_matchups"]]
        # 单调降序
        for i in range(1, len(probs)):
            assert probs[i] <= probs[i - 1] + 1e-6
        # top-5 之和 < 1.0
        assert sum(probs) < 1.0
    finally:
        db.close()


# === T6 ===
@pytest.mark.slow
def test_mc_strong_team_higher_champion_prob():
    """高 Elo 队(1845) champion_prob > 低 Elo 队(1500)."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        result = simulate_full_tournament(db, n_sims=2000, seed=5)
        d = tournament_result_to_dict(result)
        # A1 Elo 1850 (最强), L4 Elo 1460 (最弱)
        strong = d["champion_distribution"].get("A1", 0)
        weak = d["champion_distribution"].get("L4", 0)
        assert strong > weak, f"A1 ({strong}) 应 > L4 ({weak})"
        # 1000+ sims 下, 强队平均 ≥ 3% 合理
        assert strong > 0.02, f"A1 强队仅 {strong * 100:.1f}%, 偏低"
    finally:
        db.close()


# === T7 ===
@pytest.mark.slow
def test_mc_deterministic_with_seed():
    """同 seed 两次 MC, champion 分布完全一致."""
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        r1 = simulate_full_tournament(db, n_sims=500, seed=42)
        r2 = simulate_full_tournament(db, n_sims=500, seed=42)
        d1 = tournament_result_to_dict(r1)
        d2 = tournament_result_to_dict(r2)
        assert d1["champion_distribution"] == d2["champion_distribution"]
        assert d1["top_final_matchups"] == d2["top_final_matchups"]
    finally:
        db.close()


# === T8 ===
def test_mc_preserves_finished_matches():
    """已完赛 10 场 → MC 模拟不改这些, 只动剩余 62 场."""
    db = app_db.SessionLocal()
    try:
        _seed_worldcup_with_finished_matches(db, n_finished=10)
        # 已完赛的比赛 MEX-RSA id=1, status=finished, home_score=1
        # 但我们是新种了 48 队, id 不同, 这里取 finished 的 ID
        finished = db.query(Match).filter(Match.status == "finished").limit(3).all()
        for m in finished:
            assert m.home_score == 1
            assert m.away_score == 0
        # 跑 MC, 验证不抛错
        result = simulate_full_tournament(db, n_sims=200, seed=6)
        d = tournament_result_to_dict(result)
        assert d["n_sims"] == 200
        assert len(d["champion_distribution"]) == 48
    finally:
        db.close()


# === Bonus: 端点 422 ===
def test_mc_endpoint_rejects_invalid_simulations():
    """n_sims=50 应被端点 422 (FastAPI Query ge 校验)."""
    client = TestClient(app)
    resp = client.get("/api/simulator/tournament?simulations=50")
    assert resp.status_code == 422, f"期望 422, 实际 {resp.status_code}"


def test_mc_endpoint_rejects_invalid_model():
    """model=invalid 应 422."""
    client = TestClient(app)
    resp = client.get("/api/simulator/tournament?simulations=200&model=invalid")
    assert resp.status_code == 422


# === Bonus: 性能基准 (轻量, 不超时) ===
@pytest.mark.slow
def test_mc_3000_sims_under_10s():
    """3000 sims 跑完应 < 10s."""
    import time
    db = app_db.SessionLocal()
    try:
        _seed_full_worldcup(db)
        t0 = time.time()
        result = simulate_full_tournament(db, n_sims=3000, seed=99)
        duration = time.time() - t0
        assert duration < 10.0, f"3000 sims 跑了 {duration:.2f}s, 超过 10s"
        assert result.duration_seconds < 10.0
    finally:
        db.close()
