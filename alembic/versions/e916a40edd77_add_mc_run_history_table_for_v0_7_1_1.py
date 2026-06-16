"""add mc_run_history table for v0.7.1.1

Revision ID: e916a40edd77
Revises: c3e8b5f2a9d1
Create Date: 2026-06-16 14:11:24.572837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e916a40edd77'
down_revision: Union[str, None] = 'c3e8b5f2a9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mc_run_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=20), nullable=False),
        sa.Column('n_sims', sa.Integer(), nullable=False),
        sa.Column('seed', sa.Integer(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('duration_seconds', sa.Float(), nullable=False),
        sa.Column('champion_distribution', sa.Text(), nullable=False),
        sa.Column('finalist_distribution', sa.Text(), nullable=False),
        sa.Column('semifinalist_distribution', sa.Text(), nullable=False),
        sa.Column('quarterfinalist_distribution', sa.Text(), nullable=False),
        sa.Column('r16_distribution', sa.Text(), nullable=False),
        sa.Column('r32_distribution', sa.Text(), nullable=False),
        sa.Column('group_advance_probability', sa.Text(), nullable=False),
        sa.Column('top_final_matchups', sa.Text(), nullable=False),
        sa.Column('top_semifinal_matchups', sa.Text(), nullable=False),
        sa.Column('n_teams', sa.Integer(), nullable=False),
        sa.Column('n_groups', sa.Integer(), nullable=False),
        sa.Column('total_matches_per_sim', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sqlite_autoincrement=True
    )
    with op.batch_alter_table('mc_run_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mc_run_history_generated_at'), ['generated_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_mc_run_history_model'), ['model'], unique=False)
        batch_op.create_index(batch_op.f('ix_mc_run_history_n_sims'), ['n_sims'], unique=False)
        batch_op.create_index(batch_op.f('ix_mc_run_history_seed'), ['seed'], unique=False)
        batch_op.create_index('ix_mc_run_history_lookup', ['model', 'n_sims', 'seed', 'generated_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('mc_run_history', schema=None) as batch_op:
        batch_op.drop_index('ix_mc_run_history_lookup')
        batch_op.drop_index(batch_op.f('ix_mc_run_history_seed'))
        batch_op.drop_index(batch_op.f('ix_mc_run_history_n_sims'))
        batch_op.drop_index(batch_op.f('ix_mc_run_history_model'))
        batch_op.drop_index(batch_op.f('ix_mc_run_history_generated_at'))
    op.drop_table('mc_run_history')
