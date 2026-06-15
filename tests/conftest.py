"""pytest 配置：测试时使用临时 SQLite，测试间隔离."""

import sys
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# 把项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _seed_test_data(engine) -> None:
    """向临时 DB 写入最少可运行测试数据."""
    from app.db import Base, SessionLocal
    from app.models import Team, Stadium, Match

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        home = Team(id=1, fifa_code="MEX", name_zh="墨西哥", name_en="Mexico", group_name="A", flag_emoji="🇲🇽", elo_rating=1700)
        away = Team(id=2, fifa_code="RSA", name_zh="南非", name_en="South Africa", group_name="A", flag_emoji="🇿🇦", elo_rating=1500)
        stadium = Stadium(id=1, name_zh="Estadio Azteca", name_en="Estadio Azteca, Mexico City", city="Mexico City", country="Mexico", timezone="America/Mexico_City")
        match = Match(
            id=1, match_number=1, stage="小组赛", group_name="A", round_number=1,
            kickoff_at=datetime(2026, 6, 11, 19, 0),
            stadium_id=1, home_team_id=1, away_team_id=2,
            home_score=None, away_score=None, status="scheduled", data_source="manual",
        )
        db.add_all([home, away, stadium, match])
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _temp_db():
    """每个测试用独立临时 SQLite，测试间隔离."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    import app.db

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    new_engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=new_engine)
    Base.metadata.create_all(bind=new_engine)

    new_session = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
    app.db.engine = new_engine
    app.db.SessionLocal = new_session

    _seed_test_data(new_engine)

    yield

    try:
        os.unlink(tmp.name)
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
