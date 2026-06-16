"""v0.7.1 Monte Carlo Tournament E2E 端到端测试.

覆盖 3 场景:
  1. 基础契约: GET /api/simulator/tournament?simulations=1000 → 200 + champion_dist 非空
  2. model 降级: ?model=elo 也能跑(单模型)
  3. 性能基准: 10000 sims < 15s (实际应该 < 5s)

依赖: 服务需先启动 (uvicorn app.main:app --port 8000)
"""
import time

import pytest


# === 性能基准 ===
def test_mc_performance_10k_sims_under_15s():
    """10000 sims 端到端 < 15s (含 HTTP overhead, 实际 API ~5s).

    不依赖服务器,直接测服务函数。
    """
    from app import db as app_db
    from app.services.monte_carlo import simulate_full_tournament

    db = app_db.SessionLocal()
    try:
        # 需要有 48 队 + 72 场,使用 conftest 提供的生产 DB
        t0 = time.time()
        result = simulate_full_tournament(db, n_sims=10000, seed=42)
        duration = time.time() - t0
        assert duration < 15.0, f"10000 sims 跑了 {duration:.2f}s, 超 15s 预算"
        assert result.n_sims == 10000
        # 至少有 32 队参与
        assert len(result.champion_distribution) >= 32
    finally:
        db.close()


def test_mc_endpoint_returns_200_with_champion_dist(page, base_url):
    """GET /api/simulator/tournament?simulations=500 → 200."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/simulator/tournament?simulations=500');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200, f"got {resp['status']}: {resp['body']}"
    body = resp["body"]
    assert "champion_distribution" in body
    assert isinstance(body["champion_distribution"], dict)
    assert len(body["champion_distribution"]) >= 32
    # 冠军分布概率和 ~ 1.0
    total = sum(body["champion_distribution"].values())
    assert abs(total - 1.0) < 0.05, f"冠军概率和={total}, 应 ~1.0"
    # 决赛对 top-N 存在
    assert "top_final_matchups" in body
    assert isinstance(body["top_final_matchups"], list)
    assert len(body["top_final_matchups"]) > 0


def test_mc_endpoint_with_model_elo(page, base_url):
    """?model=elo 也能跑(单模型降级)."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/simulator/tournament?simulations=300&model=elo');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200, f"got {resp['status']}"
    body = resp["body"]
    assert body["model"] == "elo"
    assert "champion_distribution" in body


def test_mc_endpoint_with_model_glicko2(page, base_url):
    """?model=glicko2 也能跑(单模型)."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/simulator/tournament?simulations=300&model=glicko2');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200, f"got {resp['status']}"
    body = resp["body"]
    assert body["model"] == "glicko2"


def test_mc_endpoint_invalid_model_returns_422(page, base_url):
    """?model=invalid → 422."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/simulator/tournament?simulations=300&model=invalid');
            return r.status;
        }"""
    )
    assert resp == 422


def test_mc_endpoint_rejects_n_sims_too_small(page, base_url):
    """?simulations=50 → 422 (FastAPI Query ge 校验)."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/simulator/tournament?simulations=50');
            return r.status;
        }"""
    )
    assert resp == 422
