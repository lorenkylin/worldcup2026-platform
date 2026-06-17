"""v0.11 Forward-Testing 字段

修订 ID: k2l5m8n3p7q9
父修订: f3a9b2c1d4e6
创建时间: 2026-06-17 12:40:00.000000

修改:
- prediction_log.is_live BOOLEAN DEFAULT 0 (False) — 区分 backfill vs live
- prediction_log.snapshot_group VARCHAR(40) — 同一比赛同模型多次预测的快照组
- 索引: snapshot_group

迁移策略:
- 现有 1860+ 行 backfill 全部保留 is_live=False
- lifespan startup + 6h scheduler 写入预测时 is_live=True
- snapshot_group 默认为 NULL (无快照组概念, 一次性写入)
"""
from alembic import op
import sqlalchemy as sa


# 修订 ID, 由 alembic 自动管理
revision = "k2l5m8n3p7q9"
down_revision = "f3a9b2c1d4e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加 v0.11 Forward-Testing 字段."""
    op.add_column(
        "prediction_log",
        sa.Column(
            "is_live",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),  # SQLite boolean = 0/1
            comment="True=赛前实时预测 / False=backfill 历史回填",
        ),
    )
    op.add_column(
        "prediction_log",
        sa.Column(
            "snapshot_group",
            sa.String(length=40),
            nullable=True,
            comment="同一比赛同模型多次预测的快照组 (如赛前 7d/3d/1d)",
        ),
    )
    # 索引: snapshot_group
    op.create_index(
        "ix_prediction_log_snapshot_group",
        "prediction_log",
        ["snapshot_group"],
        unique=False,
    )


def downgrade() -> None:
    """回滚 v0.11 Forward-Testing 字段."""
    op.drop_index("ix_prediction_log_snapshot_group", table_name="prediction_log")
    op.drop_column("prediction_log", "snapshot_group")
    op.drop_column("prediction_log", "is_live")
