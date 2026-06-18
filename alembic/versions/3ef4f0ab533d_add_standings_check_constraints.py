"""add standings check constraints

Revision ID: 3ef4f0ab533d
Revises: 434e91a025fa
Create Date: 2026-06-18 11:00:04.818123

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = '3ef4f0ab533d'
down_revision: Union[str, None] = '434e91a025fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_row(played, won, drawn, lost, points):
    """修正一条积分榜记录；无法修正返回 None."""
    raw_values = (played, won, drawn, lost)
    # 任何核心计数为负数均视为不可修正（源数据损坏），直接删除
    if any(v is not None and int(v) < 0 for v in raw_values):
        return None

    p = max(int(played or 0), 0)
    w = max(int(won or 0), 0)
    d = max(int(drawn or 0), 0)
    l = max(int(lost or 0), 0)

    if w + d + l != p:
        # 优先用 played + won + drawn 反推 lost
        new_l = p - w - d
        if new_l >= 0:
            l = new_l
        else:
            # 其次用 played + won + lost 反推 drawn
            new_d = p - w - l
            if new_d >= 0:
                d = new_d
            else:
                # 最后用 played + drawn + lost 反推 won
                new_w = p - d - l
                if new_w >= 0:
                    w = new_w
                else:
                    return None

    # 积分严格按胜平公式计算
    pts = w * 3 + d
    return p, w, d, l, pts


def upgrade() -> None:
    """清理脏数据并添加 standings 检查约束."""
    if context.is_offline_mode():
        # offline 模式 (--sql) 不连真实数据库，仅添加约束
        _add_constraints()
        return

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        rows = session.execute(
            sa.text(
                "SELECT id, played, won, drawn, lost, points FROM standings"
            )
        ).all()

        update_rows = []
        delete_ids = []
        for row in rows:
            normalized = _normalize_row(
                row.played, row.won, row.drawn, row.lost, row.points
            )
            if normalized is None:
                delete_ids.append(row.id)
            else:
                update_rows.append((row.id, *normalized))

        for row_id, p, w, d, l, pts in update_rows:
            session.execute(
                sa.text(
                    """
                    UPDATE standings
                    SET played = :p, won = :w, drawn = :d,
                        lost = :l, points = :pts
                    WHERE id = :id
                    """
                ),
                {"p": p, "w": w, "d": d, "l": l, "pts": pts, "id": row_id},
            )

        if delete_ids:
            session.execute(
                sa.text("DELETE FROM standings WHERE id IN :ids"),
                {"ids": tuple(delete_ids)},
            )

        session.commit()
    finally:
        session.close()

    _add_constraints()


def _add_constraints() -> None:
    with op.batch_alter_table("standings", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_standings_played_nonneg", sa.text("played >= 0")
        )
        batch_op.create_check_constraint(
            "ck_standings_won_nonneg", sa.text("won >= 0")
        )
        batch_op.create_check_constraint(
            "ck_standings_drawn_nonneg", sa.text("drawn >= 0")
        )
        batch_op.create_check_constraint(
            "ck_standings_lost_nonneg", sa.text("lost >= 0")
        )
        batch_op.create_check_constraint(
            "ck_standings_match_count",
            sa.text("won + drawn + lost = played"),
        )
        batch_op.create_check_constraint(
            "ck_standings_points_formula",
            sa.text("points = won * 3 + drawn"),
        )


def downgrade() -> None:
    """移除 standings 检查约束."""
    with op.batch_alter_table("standings", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_standings_played_nonneg", type_="check"
        )
        batch_op.drop_constraint(
            "ck_standings_won_nonneg", type_="check"
        )
        batch_op.drop_constraint(
            "ck_standings_drawn_nonneg", type_="check"
        )
        batch_op.drop_constraint(
            "ck_standings_lost_nonneg", type_="check"
        )
        batch_op.drop_constraint(
            "ck_standings_match_count", type_="check"
        )
        batch_op.drop_constraint(
            "ck_standings_points_formula", type_="check"
        )
