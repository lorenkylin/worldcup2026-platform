"""v0.13 清理孤儿表 odds_api_cache

修订 ID: e1bc3cd68e68
父修订: ccd9db6f49a1
创建时间: 2026-06-17

修改:
- 删除历史遗留的 odds_api_cache 表(不在 models.py 中,无业务代码引用,0 行)
"""
from alembic import op
import sqlalchemy as sa

from app.alembic_helpers import get_inspector


revision = "e1bc3cd68e68"
down_revision = "ccd9db6f49a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """删除 odds_api_cache 孤儿表."""
    inspector = get_inspector(op.get_bind())
    if "odds_api_cache" in inspector.get_table_names():
        op.drop_table("odds_api_cache")


def downgrade() -> None:
    """回滚: 重建 odds_api_cache 表(最小结构,保留历史兼容性)."""
    inspector = get_inspector(op.get_bind())
    if "odds_api_cache" not in inspector.get_table_names():
        op.create_table(
            "odds_api_cache",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=512), nullable=True),
            sa.Column("response", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
