"""v0.8.1: clean up v7c/v7d calibrated prediction_log rows (sunset)

Revision ID: f3a9b2c1d4e6
Revises: e916a40edd77
Create Date: 2026-06-17 10:58:00.000000

v0.8.1 关停 G2 校准 (Platt + Isotonic) — brier 改进未达 1.5pp 门槛,
端点返回 410,UI tab 移除,Cockpit mini-card 移除。
历史 prediction_log 中 v7c/v7d model 行仅用于复盘,清理避免污染 3 模型横评。
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a9b2c1d4e6"
down_revision = "e916a40edd77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # 清 v7c_calibrated (含 _both/_platt/_isotonic 三种 method) + v7d_calibrated_isotonic
    result = conn.execute(
        sa.text(
            "DELETE FROM prediction_log "
            "WHERE model_version LIKE 'v7c_calibrated%' "
            "   OR model_version LIKE 'v7d_calibrated%'"
        )
    )
    print(f"[v0.8.1] cleaned {result.rowcount} calibrated prediction_log rows")


def downgrade() -> None:
    # 不可逆: 已删除的历史行无备份。git 保留 v0.7.8/9/10 端点代码可手工恢复。
    pass
