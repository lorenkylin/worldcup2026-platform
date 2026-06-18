"""pytest 配置：测试时使用临时 SQLite，测试间隔离.

优化(v0.13.0):
- 每个测试仍用独立 DB，但改为"模板文件拷贝"，避免每测试重复 create_all/schema 创建.
- 模板 DB 在第一次需要时生成，包含 schema + 最少种子数据.
"""

import atexit
import shutil
import sys
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# 把项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# 模板 DB 路径，惰性生成
_TEMPLATE_DB_PATH: Path | None = None


def _seed_test_data(engine) -> None:
    """向临时 DB 写入最少可运行测试数据."""
    from sqlalchemy.orm import sessionmaker
    from app.models import Team, Stadium, Match

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        home = Team(id=1, fifa_code="MEX", name_zh="墨西哥", name_en="Mexico", group_name="A", flag_emoji="🇲🇽", elo_rating=1700)
        away = Team(id=2, fifa_code="RSA", name_zh="南非", name_en="South Africa", group_name="A", flag_emoji="🇿🇦", elo_rating=1500)
        stadium = Stadium(id=1, name_zh="Estadio Azteca", name_en="Estadio Azteca, Mexico City", city="Mexico City", country="Mexico", timezone="America/Mexico_City")
        # 19:00 Mexico City (CDT UTC-5) -> 00:00 UTC next day
        kickoff_utc = (
            datetime(2026, 6, 11, 19, 0)
            .replace(tzinfo=ZoneInfo("America/Mexico_City"))
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        match = Match(
            id=1, match_number=1, stage="小组赛", group_name="A", round_number=1,
            kickoff_at=kickoff_utc,
            stadium_id=1, home_team_id=1, away_team_id=2,
            home_score=None, away_score=None, status="scheduled", data_source="manual",
        )
        db.add_all([home, away, stadium, match])
        db.commit()
    finally:
        db.close()


def _ensure_template_db() -> Path:
    """生成一份干净的模板 SQLite 文件（含 schema + 种子），供后续测试拷贝."""
    global _TEMPLATE_DB_PATH
    if _TEMPLATE_DB_PATH is not None and _TEMPLATE_DB_PATH.exists():
        return _TEMPLATE_DB_PATH

    from sqlalchemy import create_engine
    from app.db import Base
    from app.models import Team, Stadium, Match  # noqa: F401 确保 Base metadata 注册所有表

    fd, path = tempfile.mkstemp(suffix="_template.db")
    os.close(fd)
    template_path = Path(path)

    engine = create_engine(
        f"sqlite:///{template_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_test_data(engine)
    engine.dispose()

    _TEMPLATE_DB_PATH = template_path
    return template_path


def _cleanup_template_db() -> None:
    """进程退出时删除模板 DB."""
    global _TEMPLATE_DB_PATH
    if _TEMPLATE_DB_PATH is not None:
        try:
            os.unlink(_TEMPLATE_DB_PATH)
        except OSError:
            pass
        _TEMPLATE_DB_PATH = None


atexit.register(_cleanup_template_db)


@pytest.fixture(autouse=True)
def _temp_db():
    """每个测试用独立临时 SQLite（从模板拷贝），测试间隔离."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.db

    template_path = _ensure_template_db()

    fd, dst_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    shutil.copy(str(template_path), dst_path)

    new_engine = create_engine(
        f"sqlite:///{dst_path}",
        connect_args={"check_same_thread": False},
    )
    new_session = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
    app.db.engine = new_engine
    app.db.SessionLocal = new_session

    yield

    new_engine.dispose()
    try:
        os.unlink(dst_path)
    except OSError:
        pass


@pytest.fixture
def db_session():
    """提供已绑定到临时数据库的 Session 实例."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
