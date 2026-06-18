"""v0.13 补充 prediction_log.is_live 索引

修订 ID: ccd9db6f49a1
父修订: k2l5m8n3p7q9
创建时间: 2026-06-17

修改:
- 为 prediction_log.is_live 添加索引 ix_prediction_log_is_live

背景:
- v0.11 迁移添加了 is_live 列并标记 index=True,但漏建索引.
- /api/elo/live-accuracy 等按 is_live 过滤的查询会全表扫描.
"""
from alembic import op

from app.alembic_helpers import get_inspector


revision = "ccd9db6f49a1"
down_revision = "k2l5m8n3p7q9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加 is_live 索引."""
    inspector = get_inspector(op.get_bind())
    index_names = {idx['name'] for idx in inspector.get_indexes('prediction_log')}
    if 'ix_prediction_log_is_live' not in index_names:
        op.create_index(
            "ix_prediction_log_is_live",
            "prediction_log",
            ["is_live"],
            unique=False,
        )


def downgrade() -> None:
    """回滚 is_live 索引."""
    inspector = get_inspector(op.get_bind())
    index_names = {idx['name'] for idx in inspector.get_indexes('prediction_log')}
    if 'ix_prediction_log_is_live' in index_names:
        op.drop_index("ix_prediction_log_is_live", table_name="prediction_log")
