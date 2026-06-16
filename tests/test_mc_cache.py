"""v0.7.1.1 Monte Carlo 缓存单元/集成测试."""
from datetime import datetime, timedelta, timezone

import pytest

from app import db as app_db
from app.models import MCRunHistory
from app.services.monte_carlo import (
    MC_CACHE_TTL_SECONDS,
    load_mc_cache,
    save_mc_cache,
    run_mc_with_cache,
    simulate_full_tournament,
    DEFAULT_SIMULATIONS,
)


@pytest.fixture
def db():
    session = app_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_minimal_worldcup(db):
    """复用 v0.7.1 测试的 48 队 seed,清空可能冲突的 conftest 数据."""
    from tests.test_monte_carlo import _seed_full_worldcup
    _seed_full_worldcup(db)


def test_save_and_load_mc_cache(db):
    """T1: save 后 load 能命中,dict 与原 TournamentResult 等价."""
    _seed_minimal_worldcup(db)
    result = simulate_full_tournament(db, n_sims=200, seed=42)

    save_mc_cache(db, model="blend", n_sims=200, seed=42, result=result)

    cached = load_mc_cache(db, model="blend", n_sims=200, seed=42)
    assert cached is not None
    assert cached["n_sims"] == result.n_sims
    assert cached["model"] == result.model
    assert cached["champion_distribution"] == result.champion_distribution
    assert cached["top_final_matchups"] == result.top_final_matchups
    assert cached["cached"] is True
    assert cached["cache_age_seconds"] < 5


def test_mc_cache_ttl_expired(db):
    """T2: 把 generated_at 改到 7h 前,load 返回 None."""
    _seed_minimal_worldcup(db)
    result = simulate_full_tournament(db, n_sims=200, seed=42)
    save_mc_cache(db, model="blend", n_sims=200, seed=42, result=result)

    row = db.query(MCRunHistory).first()
    row.generated_at = datetime.now(timezone.utc) - timedelta(hours=7)
    db.commit()

    cached = load_mc_cache(db, model="blend", n_sims=200, seed=42)
    assert cached is None


def test_mc_cache_refresh_param_bypasses_cache(db):
    """T3: refresh=True 时即使缓存存在也重新计算."""
    _seed_minimal_worldcup(db)
    result1 = simulate_full_tournament(db, n_sims=200, seed=42)
    save_mc_cache(db, model="blend", n_sims=200, seed=42, result=result1)

    result2 = run_mc_with_cache(
        db,
        n_sims=200,
        model="blend",
        return_top_n=8,
        seed=42,
        refresh=True,
    )
    assert "cached" not in result2 or result2.get("cached") is False
    # refresh 后应有新缓存
    cached = load_mc_cache(db, model="blend", n_sims=200, seed=42)
    assert cached is not None


def test_run_mc_with_cache_uses_cache(db):
    """T4: 先写缓存,再调 run_mc_with_cache,返回 cached 结果且 duration_seconds 为旧值."""
    _seed_minimal_worldcup(db)
    result = simulate_full_tournament(db, n_sims=200, seed=42)
    result.duration_seconds = 1.234
    save_mc_cache(db, model="blend", n_sims=200, seed=42, result=result)

    out = run_mc_with_cache(
        db,
        n_sims=200,
        model="blend",
        return_top_n=8,
        seed=42,
        refresh=False,
    )
    assert out.get("cached") is True
    assert out["duration_seconds"] == pytest.approx(1.234)


def test_run_mc_with_cache_computes_when_missing(db):
    """T5: 无缓存时调用,结果写入表."""
    _seed_minimal_worldcup(db)
    db.query(MCRunHistory).filter(
        MCRunHistory.model == "blend",
        MCRunHistory.n_sims == 200,
        MCRunHistory.seed == 42,
    ).delete(synchronize_session=False)
    db.commit()

    out = run_mc_with_cache(
        db,
        n_sims=200,
        model="blend",
        return_top_n=8,
        seed=42,
        refresh=False,
    )
    assert out.get("cached") is not True
    assert out["n_sims"] == 200

    row = db.query(MCRunHistory).filter(
        MCRunHistory.model == "blend",
        MCRunHistory.n_sims == 200,
        MCRunHistory.seed == 42,
    ).first()
    assert row is not None


def test_mc_cache_default_params_use_default_ttl(db):
    """T6: 默认参数 (blend/10000/seed=42) 在 6h 内视为有效."""
    _seed_minimal_worldcup(db)
    result = simulate_full_tournament(db, n_sims=200, seed=42)
    save_mc_cache(db, model="blend", n_sims=200, seed=42, result=result)

    cached = load_mc_cache(
        db,
        model="blend",
        n_sims=200,
        seed=42,
        ttl_seconds=MC_CACHE_TTL_SECONDS,
    )
    assert cached is not None


def test_mc_cache_different_keys_are_independent(db):
    """T7: 不同 (model, n_sims, seed) 互不影响."""
    _seed_minimal_worldcup(db)
    result = simulate_full_tournament(db, n_sims=200, seed=42)
    save_mc_cache(db, model="blend", n_sims=200, seed=42, result=result)

    assert load_mc_cache(db, model="elo", n_sims=200, seed=42) is None
    assert load_mc_cache(db, model="blend", n_sims=500, seed=42) is None
    assert load_mc_cache(db, model="blend", n_sims=200, seed=99) is None
