"""数据库连接与依赖注入模块.

使用 SQLAlchemy 2.0 异步风格简化实现；SQLite 同步引擎足以支撑个人项目。
"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.config import settings


# 健壮化 database_url 解析：支持绝对路径、DATA_DIR=/data、Windows 盘符、内存库等
_url = make_url(settings.database_url)
if _url.drivername == "sqlite":
    _db_path_part = _url.database
    if _db_path_part and _db_path_part != ":memory:":
        db_path = Path(_db_path_part).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

# SQLite 需要 check_same_thread=False 才能在多线程 FastAPI 依赖中复用
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.debug,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """启用 SQLite 外键约束."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Session:
    """FastAPI 依赖：生成数据库会话并在请求结束后关闭."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
