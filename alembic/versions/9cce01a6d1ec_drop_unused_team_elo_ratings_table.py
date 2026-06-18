"""drop unused team_elo_ratings table

Revision ID: 9cce01a6d1ec
Revises: 3ef4f0ab533d
Create Date: 2026-06-18 11:07:53.074165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.alembic_helpers import get_inspector


# revision identifiers, used by Alembic.
revision: str = '9cce01a6d1ec'
down_revision: Union[str, None] = '3ef4f0ab533d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # team_elo_ratings 为 M1 历史保留表，当前运行时代码已不再读取，且线上为 0 行。
    # 有限上线前清理死表，减少 Schema 噪音与迁移维护成本。
    inspector = get_inspector(op.get_bind())
    if 'team_elo_ratings' in inspector.get_table_names():
        with op.batch_alter_table('team_elo_ratings', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_team_elo_ratings_team_id'))
            batch_op.drop_index(batch_op.f('ix_team_elo_ratings_id'))
            batch_op.drop_index(batch_op.f('ix_team_elo_ratings_as_of_date'))
        op.drop_table('team_elo_ratings')


def downgrade() -> None:
    inspector = get_inspector(op.get_bind())
    if 'team_elo_ratings' not in inspector.get_table_names():
        op.create_table(
            'team_elo_ratings',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('team_id', sa.Integer(), nullable=False),
            sa.Column('as_of_date', sa.DateTime(), nullable=False),
            sa.Column('rating', sa.Float(), nullable=False),
            sa.Column('rank', sa.Integer(), nullable=True),
            sa.Column('source', sa.String(length=20), nullable=False),
            sa.Column('scraped_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id']),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('team_elo_ratings', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_team_elo_ratings_as_of_date'), ['as_of_date'], unique=False)
            batch_op.create_index(batch_op.f('ix_team_elo_ratings_id'), ['id'], unique=False)
            batch_op.create_index(batch_op.f('ix_team_elo_ratings_team_id'), ['team_id'], unique=False)
