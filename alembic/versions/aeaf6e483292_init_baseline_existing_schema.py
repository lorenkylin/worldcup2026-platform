"""init_baseline_existing_schema

基线迁移：把当前 schema 版本固定下来。

- 用途 A（已有 DB）：补齐 prediction_cache 上缺失的索引 ix_prediction_cache_match_id
- 用途 B（空 DB）：在 alembic upgrade head 时通过 Base.metadata.create_all() 把全部表建出来
- 所有 schema 演进从此迁移开始累积（down_revision = None）

Revision ID: aeaf6e483292
Revises:
Create Date: 2026-06-13 12:18:07.823734
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.alembic_helpers import get_inspector


# revision identifiers, used by Alembic.
revision: str = 'aeaf6e483292'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """双轨：空 DB 全表 create_all + 已有 DB 补缺失索引."""
    # 1) 兜底：空 DB 时把 Base.metadata 里所有表建出来
    #    已有 DB 时 create_all 是 no-op（IF NOT EXISTS 语义）
    from app.db import Base
    import app.models  # noqa: F401  注册全部 ORM 模型
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    # 2) 已有 DB 真实缺的索引（autogenerate 检测到 prediction_cache.match_id 上无索引）
    #    空库 create_all 已创建该索引，需先检查避免重复创建导致索引已存在错误
    inspector = get_inspector(bind)
    index_names = {idx['name'] for idx in inspector.get_indexes('prediction_cache')}
    if 'ix_prediction_cache_match_id' not in index_names:
        with op.batch_alter_table('prediction_cache', schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f('ix_prediction_cache_match_id'),
                ['match_id'],
                unique=False,
            )


def downgrade() -> None:
    """回滚到无版本状态：删索引 + 不删表（保留所有数据便于排查）.

    注意：drop_all 会清空数据，原则上不放在 baseline 迁移里。
    真正销毁 schema 请用 op.drop_table() 写显式迁移。
    """
    inspector = get_inspector(op.get_bind())
    index_names = {idx['name'] for idx in inspector.get_indexes('prediction_cache')}
    if 'ix_prediction_cache_match_id' in index_names:
        with op.batch_alter_table('prediction_cache', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_prediction_cache_match_id'))
