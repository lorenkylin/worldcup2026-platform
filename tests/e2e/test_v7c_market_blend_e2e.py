"""E2E: v0.13.0 MarketBlend 端点."""

import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "worldcup2026.db"


def _query_db(sql, params=()):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def test_elo_page_includes_marketblend_tab(page, base_url):
    """/elo 路由 1v1 对比器含 MarketBlend 按钮."""
    page.goto("about:blank")
    page.goto(f"{base_url}/#/elo", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    found = page.evaluate(
        "() => Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('市场融合'))"
    )
    assert found, "市场融合模型按钮未渲染"


def test_market_blend_endpoint_returns_market_component(page, base_url):
    """/api/elo/predict-market-blend/MEX/RSA?match_id=1 返回含 market 的三方融合."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/predict-market-blend/MEX/RSA?match_id=1');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200, f"endpoint returned {resp['status']}: {resp['body']}"
    body = resp["body"]
    assert body["model_version"] == "v7c_market_blend"
    assert body["fallback_reason"] is None
    assert "market" in body
    assert body["market"]["bookmaker"] == "betpawa"
    probs = body["blended"]["probabilities"]
    assert abs(probs["home_win"] + probs["draw"] + probs["away_win"] - 1.0) < 1e-3


def test_market_blend_writes_prediction_log(page, base_url):
    """带 match_id 时自动写 prediction_log."""
    test_mid = 27  # 使用已存在的 scheduled 比赛 ID (v0.15.0 修正)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM prediction_log WHERE match_id=? AND model_version='v7c_market_blend'",
            (test_mid,),
        )
        conn.commit()
    finally:
        conn.close()

    r = page.evaluate(
        f"""async () => {{
            const r = await fetch('/api/elo/predict-market-blend/MEX/RSA?match_id={test_mid}');
            return r.status;
        }}"""
    )
    assert r == 200

    rows = _query_db(
        "SELECT id FROM prediction_log WHERE match_id=? AND model_version='v7c_market_blend'",
        (test_mid,),
    )
    assert len(rows) == 1, f"expected 1 prediction_log row, got {len(rows)}"

    # 清理
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM prediction_log WHERE match_id=? AND model_version='v7c_market_blend'",
            (test_mid,),
        )
        conn.commit()
    finally:
        conn.close()
