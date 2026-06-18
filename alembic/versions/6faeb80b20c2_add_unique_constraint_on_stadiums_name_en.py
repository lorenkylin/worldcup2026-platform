"""add unique constraint on stadiums.name_en

修订 ID: 6faeb80b20c2
父修订: e1bc3cd68e68
创建时间: 2026-06-17

修改:
- 给 stadiums.name_en 加唯一约束，防止 seed 与 worldcup26.ir 同步产生重复球场。

注意: 执行本迁移前需确保 DB 中 name_en 无重复（可用 scripts/cleanup_v013_data.py --apply）。
"""

from alembic import context, op

from app.alembic_helpers import get_inspector


revision = "6faeb80b20c2"
down_revision = "e1bc3cd68e68"
branch_labels = None
depends_on = None


def _has_unique_name_en(inspector) -> bool:
    """检查 stadiums.name_en 是否已存在唯一约束/索引."""
    for idx in inspector.get_indexes("stadiums"):
        if idx.get("unique") and "name_en" in idx.get("column_names", []):
            return True
    return False


def upgrade() -> None:
    inspector = get_inspector(op.get_bind())
    if not _has_unique_name_en(inspector):
        if context.is_offline_mode():
            # offline (--sql) 模式下 batch_alter_table + create_unique_constraint
            # 需要反射真实表，改用 create_index 生成等效 SQL
            op.create_index("uq_stadiums_name_en", "stadiums", ["name_en"], unique=True)
        else:
            with op.batch_alter_table("stadiums") as batch_op:
                batch_op.create_unique_constraint("uq_stadiums_name_en", ["name_en"])


def downgrade() -> None:
    inspector = get_inspector(op.get_bind())
    # 空库上基线 create_all 会创建自动命名的唯一索引，而不是 uq_stadiums_name_en
    if _has_unique_name_en(inspector):
        if context.is_offline_mode():
            op.drop_index("uq_stadiums_name_en", table_name="stadiums")
        else:
            with op.batch_alter_table("stadiums") as batch_op:
                # 仅当存在显式命名的约束时才删除；自动命名的唯一索引由基线/模型管理
                batch_op.drop_constraint("uq_stadiums_name_en", type_="unique")
