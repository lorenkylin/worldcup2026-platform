"""add unique constraint on stadiums.name_en

修订 ID: 6faeb80b20c2
父修订: e1bc3cd68e68
创建时间: 2026-06-17

修改:
- 给 stadiums.name_en 加唯一约束，防止 seed 与 worldcup26.ir 同步产生重复球场。

注意: 执行本迁移前需确保 DB 中 name_en 无重复（可用 scripts/cleanup_v013_data.py --apply）。
"""

from alembic import op


revision = "6faeb80b20c2"
down_revision = "e1bc3cd68e68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stadiums") as batch_op:
        batch_op.create_unique_constraint("uq_stadiums_name_en", ["name_en"])


def downgrade() -> None:
    with op.batch_alter_table("stadiums") as batch_op:
        batch_op.drop_constraint("uq_stadiums_name_en", type_="unique")
