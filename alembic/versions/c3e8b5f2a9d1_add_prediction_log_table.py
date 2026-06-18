"""add_prediction_log_table

Revision ID: c3e8b5f2a9d1
Revises: b9c4d8e2f1a3
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.alembic_helpers import get_inspector


# revision identifiers, used by Alembic.
revision: str = "c3e8b5f2a9d1"
down_revision: Union[str, None] = "b9c4d8e2f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v0.6.0: 预测日志表 (追踪每次预测 vs 实际, 自动计算准确率)
    # 基线迁移在空库上已创建该表，需先检查避免重复创建
    inspector = get_inspector(op.get_bind())
    if "prediction_log" not in inspector.get_table_names():
        op.create_table(
            "prediction_log",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("match_id", sa.Integer(), nullable=False),
            sa.Column("model_version", sa.String(length=30), nullable=False),
            sa.Column("predicted_at", sa.DateTime(), nullable=False),
            sa.Column("pred_home_win", sa.Float(), nullable=False),
            sa.Column("pred_draw", sa.Float(), nullable=False),
            sa.Column("pred_away_win", sa.Float(), nullable=False),
            sa.Column("predicted_outcome", sa.String(length=1), nullable=False),
            sa.Column("actual_home_score", sa.Integer(), nullable=True),
            sa.Column("actual_away_score", sa.Integer(), nullable=True),
            sa.Column("actual_outcome", sa.String(length=4), nullable=True),
            sa.Column("correct", sa.Integer(), nullable=True),
            sa.Column("brier_score", sa.Float(), nullable=True),
            sa.Column("log_loss", sa.Float(), nullable=True),
            sa.Column("elo_home", sa.Integer(), nullable=True),
            sa.Column("elo_away", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=True),
            sa.Column("settled_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_prediction_log_match_id"),
        )
        op.create_index("ix_prediction_log_id", "prediction_log", ["id"])
        op.create_index("ix_prediction_log_match_id", "prediction_log", ["match_id"])
        op.create_index("ix_prediction_log_model_version", "prediction_log", ["model_version"])
        op.create_index("ix_prediction_log_predicted_at", "prediction_log", ["predicted_at"])
        op.create_index("ix_prediction_log_correct", "prediction_log", ["correct"])


def downgrade() -> None:
    inspector = get_inspector(op.get_bind())
    if "prediction_log" in inspector.get_table_names():
        op.drop_index("ix_prediction_log_correct", table_name="prediction_log")
        op.drop_index("ix_prediction_log_predicted_at", table_name="prediction_log")
        op.drop_index("ix_prediction_log_model_version", table_name="prediction_log")
        op.drop_index("ix_prediction_log_match_id", table_name="prediction_log")
        op.drop_index("ix_prediction_log_id", table_name="prediction_log")
        op.drop_table("prediction_log")
