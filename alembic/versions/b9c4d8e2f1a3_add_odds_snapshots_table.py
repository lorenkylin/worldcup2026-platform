"""add_odds_snapshots_table

Revision ID: b9c4d8e2f1a3
Revises: b1c5e7f9a2d3
Create Date: 2026-06-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9c4d8e2f1a3"
down_revision: Union[str, None] = "b1c5e7f9a2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v0.5.1: 赔率快照表（走势图表数据源）
    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("bookmaker", sa.String(length=50), nullable=False),
        sa.Column("home_win", sa.Float(), nullable=True),
        sa.Column("draw", sa.Float(), nullable=True),
        sa.Column("away_win", sa.Float(), nullable=True),
        sa.Column("over_2_5", sa.Float(), nullable=True),
        sa.Column("under_2_5", sa.Float(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("odds_snapshots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_odds_snapshots_id"), ["id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_odds_snapshots_match_id"), ["match_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_odds_snapshots_bookmaker"), ["bookmaker"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_odds_snapshots_snapshot_at"), ["snapshot_at"], unique=False
        )
        # 复合索引: 单场单公司历史查询(走势图表主查询)
        batch_op.create_index(
            "ix_odds_snap_match_book_time",
            ["match_id", "bookmaker", "snapshot_at"],
            unique=False,
        )

    # 数据迁移: 把 v0.5.0 已有的 match_odds 行复制为初始 snapshot
    # 用 fetched_at 作为 snapshot_at(保持原始时间锚点)
    # 用 INSERT ... SELECT 直接从 match_odds 拷贝
    op.execute(
        """
        INSERT INTO odds_snapshots (
            match_id, bookmaker, home_win, draw, away_win,
            over_2_5, under_2_5, snapshot_at, source
        )
        SELECT
            match_id, bookmaker, home_win, draw, away_win,
            over_2_5, under_2_5,
            COALESCE(fetched_at, CURRENT_TIMESTAMP),
            COALESCE(source, 'manual') || '_seed_migrated'
        FROM match_odds
        WHERE NOT EXISTS (
            SELECT 1 FROM odds_snapshots
            WHERE odds_snapshots.match_id = match_odds.match_id
              AND odds_snapshots.bookmaker = match_odds.bookmaker
              AND odds_snapshots.snapshot_at = COALESCE(match_odds.fetched_at, CURRENT_TIMESTAMP)
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("odds_snapshots", schema=None) as batch_op:
        batch_op.drop_index("ix_odds_snap_match_book_time")
        batch_op.drop_index(batch_op.f("ix_odds_snapshots_snapshot_at"))
        batch_op.drop_index(batch_op.f("ix_odds_snapshots_bookmaker"))
        batch_op.drop_index(batch_op.f("ix_odds_snapshots_match_id"))
        batch_op.drop_index(batch_op.f("ix_odds_snapshots_id"))
    op.drop_table("odds_snapshots")
