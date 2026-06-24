"""add primary secondary score fields

Revision ID: 51373a2cff45
Revises: ed5e24f162be
Create Date: 2026-06-24 12:12:23.974904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51373a2cff45'
down_revision: Union[str, None] = 'ed5e24f162be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('prediction_cache', schema=None) as batch_op:
        batch_op.add_column(sa.Column('primary_score', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('secondary_score', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('score_reliability_stars', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('prediction_cache', schema=None) as batch_op:
        batch_op.drop_column('score_reliability_stars')
        batch_op.drop_column('secondary_score')
        batch_op.drop_column('primary_score')
