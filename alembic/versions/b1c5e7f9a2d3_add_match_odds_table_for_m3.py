"""add_match_odds_table_for_m3

Revision ID: b1c5e7f9a2d3
Revises: ae0ea4ea9892
Create Date: 2026-06-15 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c5e7f9a2d3'
down_revision: Union[str, None] = 'ae0ea4ea9892'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # M3: 比赛赔率表（市场预期视角，与 Elo 预测对比）
    op.create_table(
        'match_odds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('bookmaker', sa.String(length=50), nullable=False),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('over_2_5', sa.Float(), nullable=True),
        sa.Column('under_2_5', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('match_odds', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_match_odds_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_match_odds_match_id'), ['match_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('match_odds', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_match_odds_match_id'))
        batch_op.drop_index(batch_op.f('ix_match_odds_id'))
    op.drop_table('match_odds')
