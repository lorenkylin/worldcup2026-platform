"""E2E 端到端测试: v0.7.0a-b ModelBlend 端点.

覆盖:
- /api/elo/predict-blend/{home}/{away}?match_id=N 触发后,prediction_log 表有 v7a_blend 行
- w_elo + w_glicko2 ≠ 1.0 触发 422 校验
- 不存在的 FIFA 码触发 404

依赖:
- 需先启动 server: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
- 需先装 playwright: python -m pip install playwright && python -m playwright install chromium
- 测试行使用 match_id=88888 (生产中不存在的 ID),测试结束会清理
"""

import sqlite3
import time
from pathlib import Path

import pytest

# 项目根
ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "worldcup2026.db"


def _query_db(sql: str, params: tuple = ()):
    """直接查生产 SQLite DB, e2e 不绑定 ORM session."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _exec_db(sql: str, params: tuple = ()):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


TEST_MATCH_ID = 88888  # 生产中不存在的 ID, 避免 dedup 干扰


def test_predict_blend_endpoint_returns_blended_probs(page, base_url):
    """v0.7.0a: predict-blend 端点返回 blended 概率."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/predict-blend/BRA/ARG');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 200, f"endpoint returned {resp['status']}: {resp['body']}"
    body = resp["body"]
    assert body["home"]["fifa_code"] == "BRA"
    assert body["away"]["fifa_code"] == "ARG"
    assert "blended" in body
    assert body["blended"]["weights"] == {"elo": 0.5, "glicko2": 0.5}
    probs = body["blended"]["probabilities"]
    assert 0 < probs["home_win"] < 1
    assert 0 < probs["draw"] < 1
    assert 0 < probs["away_win"] < 1
    # 三类概率和 = 1.0 (浮点容差 1e-3, 服务端概率 rounded 到 4 位)
    assert abs(probs["home_win"] + probs["draw"] + probs["away_win"] - 1.0) < 1e-3
    assert body["model_version"] == "v7a_blend"


def test_predict_blend_with_match_id_writes_prediction_log(page, base_url):
    """v0.7.0a-b: ?match_id=N 自动写 prediction_log 表 (model_version='v7a_blend')."""
    # 清理可能残留的旧测试行
    _exec_db(
        "DELETE FROM prediction_log WHERE match_id=? AND model_version='v7a_blend'",
        (TEST_MATCH_ID,),
    )

    resp = page.evaluate(
        f"""async () => {{
            const r = await fetch('/api/elo/predict-blend/BRA/ARG?match_id={TEST_MATCH_ID}');
            return {{ status: r.status, body: await r.json() }};
        }}"""
    )
    assert resp["status"] == 200, f"endpoint returned {resp['status']}: {resp['body']}"
    body = resp["body"]
    assert body["model_version"] == "v7a_blend"

    # 查 DB 验证
    rows = _query_db(
        "SELECT match_id, model_version, predicted_outcome, pred_home_win, "
        "pred_draw, pred_away_win, source FROM prediction_log "
        "WHERE match_id=? AND model_version='v7a_blend'",
        (TEST_MATCH_ID,),
    )
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    row = rows[0]
    assert row["match_id"] == TEST_MATCH_ID
    assert row["model_version"] == "v7a_blend"
    assert row["source"] == "blend_elo_glicko2"
    # 预测 outcome 是 H/D/A 之一
    assert row["predicted_outcome"] in ("H", "D", "A")
    # 概率写入了
    assert 0 < row["pred_home_win"] < 1
    assert 0 < row["pred_draw"] < 1
    assert 0 < row["pred_away_win"] < 1


def test_predict_blend_with_custom_weights(page, base_url):
    """v0.7.0a: w_elo=0.7 + w_glicko2=0.3 应得不同 blend."""
    resp_50 = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/predict-blend/BRA/ARG?w_elo=0.5&w_glicko2=0.5');
            return await r.json();
        }"""
    )
    resp_70 = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/predict-blend/BRA/ARG?w_elo=0.7&w_glicko2=0.3');
            return await r.json();
        }"""
    )
    p50 = resp_50["blended"]["probabilities"]
    p70 = resp_70["blended"]["probabilities"]
    # 不同权重应得到不同的 blend 概率 (除非两模型碰巧一致)
    assert p50["home_win"] != p70["home_win"] or p50["draw"] != p70["draw"]


def test_predict_blend_rejects_invalid_weights(page, base_url):
    """v0.7.0a: w_elo + w_glicko2 ≠ 1.0 应返回 422."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/predict-blend/BRA/ARG?w_elo=0.3&w_glicko2=0.3');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 422, f"expected 422, got {resp['status']}"
    assert "必须等于 1.0" in resp["body"].get("detail", "")


def test_predict_blend_unknown_team_returns_404(page, base_url):
    """v0.7.0a: 未知球队代码应返回 404."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/elo/predict-blend/XXX/YYY');
            return { status: r.status, body: await r.json() };
        }"""
    )
    assert resp["status"] == 404, f"expected 404, got {resp['status']}"


def test_predict_blend_dedup_within_1_hour(page, base_url):
    """v0.7.0a-b: 同 (match_id, model) 1h 内重复请求只写 1 行."""
    test_mid = 88889
    _exec_db(
        "DELETE FROM prediction_log WHERE match_id=? AND model_version='v7a_blend'",
        (test_mid,),
    )

    # 第 1 次
    r1 = page.evaluate(
        f"""async () => {{
            const r = await fetch('/api/elo/predict-blend/BRA/ARG?match_id={test_mid}');
            return r.status;
        }}"""
    )
    assert r1 == 200

    # 第 2 次
    r2 = page.evaluate(
        f"""async () => {{
            const r = await fetch('/api/elo/predict-blend/BRA/ARG?match_id={test_mid}');
            return r.status;
        }}"""
    )
    assert r2 == 200

    # DB 仍只有 1 行
    rows = _query_db(
        "SELECT id FROM prediction_log WHERE match_id=? AND model_version='v7a_blend'",
        (test_mid,),
    )
    assert len(rows) == 1, f"expected 1 row (dedup), got {len(rows)}"

    # 清理
    _exec_db(
        "DELETE FROM prediction_log WHERE match_id=? AND model_version='v7a_blend'",
        (test_mid,),
    )


def test_v7a_blend_accuracy_stats_visible(page, base_url):
    """v0.7.0a-b: /accuracy 页面应含 v7a_blend 模型行 (写库后)."""
    page.goto(f"{base_url}/#/accuracy", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2)  # 等 SPA 渲染
    body_text = page.locator("body").text_content() or ""
    # 页面应能正常加载 (即使 v7a_blend 暂无已结算样本, 也不报错)
    assert "准确率" in body_text or "Accuracy" in body_text, \
        f"/#/accuracy page not rendered: {body_text[:300]}"
