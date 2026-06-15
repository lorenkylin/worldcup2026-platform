"""数据库连接与依赖注入模块.

使用 SQLAlchemy 2.0 异步风格简化实现；SQLite 同步引擎足以支撑个人项目。
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.config import settings


# 确保数据库目录存在
db_path = Path(settings.database_url.replace("sqlite:///./", "")).resolve()
db_path.parent.mkdir(parents=True, exist_ok=True)

# SQLite 需要 check_same_thread=False 才能在多线程 FastAPI 依赖中复用
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Session:
    """FastAPI 依赖：生成数据库会话并在请求结束后关闭."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
