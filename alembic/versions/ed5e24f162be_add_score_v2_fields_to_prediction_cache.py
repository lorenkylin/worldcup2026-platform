"""add score v2 fields to prediction_cache

Revision ID: ed5e24f162be
Revises: 9cce01a6d1ec
Create Date: 2026-06-24 11:56:02.631136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed5e24f162be'
down_revision: Union[str, None] = '9cce01a6d1ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('prediction_cache', schema=None) as batch_op:
        batch_op.add_column(sa.Column('outcome_aligned_score', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('top_scores', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('score_confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('prediction_cache', schema=None) as batch_op:
        batch_op.drop_column('score_confidence')
        batch_op.drop_column('top_scores')
        batch_op.drop_column('outcome_aligned_score')
