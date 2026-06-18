"""convert_match_kickoff_to_utc

Revision ID: 434e91a025fa
Revises: 6faeb80b20c2
Create Date: 2026-06-17 17:32:13.330369

"""
from datetime import datetime, timezone
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = '434e91a025fa'
down_revision: Union[str, None] = '6faeb80b20c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _parse_dt(value):
    """兼容 SQLite 返回 str 或 datetime 的情况."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def upgrade() -> None:
    """将 matches.kickoff_at 从球场本地墙钟时间统一转换为 UTC naive.

    转换前：kickoff_at 存的是 stadium-local naive datetime（如美东 15:00）。
    转换后：按 stadium.timezone 解析为 aware，再转 UTC 并去掉 tzinfo。
    """
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        rows = session.execute(
            sa.text(
                """
                SELECT m.id, m.kickoff_at, s.timezone
                FROM matches m
                LEFT JOIN stadiums s ON m.stadium_id = s.id
                WHERE m.kickoff_at IS NOT NULL
                """
            )
        ).all()

        for row in rows:
            kickoff = _parse_dt(row.kickoff_at)
            if kickoff is None:
                continue
            tz_name = row.timezone or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")
            local = kickoff.replace(tzinfo=tz)
            utc = local.astimezone(timezone.utc).replace(tzinfo=None)
            session.execute(
                sa.text("UPDATE matches SET kickoff_at = :utc WHERE id = :id"),
                {"utc": utc, "id": row.id},
            )
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    """降级操作：将 UTC naive 重新转回球场本地墙钟时间."""
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        rows = session.execute(
            sa.text(
                """
                SELECT m.id, m.kickoff_at, s.timezone
                FROM matches m
                LEFT JOIN stadiums s ON m.stadium_id = s.id
                WHERE m.kickoff_at IS NOT NULL
                """
            )
        ).all()

        for row in rows:
            kickoff = _parse_dt(row.kickoff_at)
            if kickoff is None:
                continue
            tz_name = row.timezone or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")
            utc = kickoff.replace(tzinfo=timezone.utc)
            local = utc.astimezone(tz).replace(tzinfo=None)
            session.execute(
                sa.text("UPDATE matches SET kickoff_at = :local WHERE id = :id"),
                {"local": local, "id": row.id},
            )
        session.commit()
    finally:
        session.close()
