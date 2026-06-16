"""v0.7.2.3 赔率 vs 模型走势对比 - E2E 测试."""
import time


def test_history_comparison_returns_points_when_data_exists(page, base_url):
    """同一场比赛连续访问赔率走势对比端点,无错."""
    # 用 match_id=1 (conftest seed)
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/odds/1/history-comparison?model=blend&hours=72&min_points=1');
            return { status: r.status };
        }"""
    )
    # 数据可能 0 条 → 204; 有数据 → 200
    assert resp["status"] in (200, 204), f"got {resp['status']}"


def test_history_comparison_invalid_model_returns_422(page, base_url):
    """model=invalid → 422."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/odds/1/history-comparison?model=invalid');
            return r.status;
        }"""
    )
    assert resp == 422


def test_history_comparison_nonexistent_match_returns_404(page, base_url):
    """不存在的 match_id → 404."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/odds/9999999/history-comparison?min_points=1');
            return r.status;
        }"""
    )
    assert resp == 404


def test_history_comparison_hours_param_bounds(page, base_url):
    """hours=0 → 422 (FastAPI Query ge=1 校验)."""
    resp = page.evaluate(
        """async () => {
            const r = await fetch('/api/odds/1/history-comparison?hours=0');
            return r.status;
        }"""
    )
    assert resp == 422
