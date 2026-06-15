"""Alembic 迁移环境.

- 接入 app.config.settings（统一从 .env 读取数据库 URL，避免硬编码漂移）
- 接入 app.db.Base + app.models（确保所有 ORM 模型已注册到 Base.metadata）
- 支持 offline (SQL 输出) 与 online (DB 直连) 双模式
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# 1. 让 Alembic 找到 app 包（prepend_sys_path=. 已在 alembic.ini 中设置）
# ---------------------------------------------------------------------------
from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
import app.models  # noqa: F401,E402  # 关键：导入让 Base.metadata 注册全部表

# ---------------------------------------------------------------------------
# 2. Alembic 基础配置
# ---------------------------------------------------------------------------
config = context.config

# 用 .env 中的实际 URL 覆盖 alembic.ini 的占位 URL
config.set_main_option("sqlalchemy.url", settings.database_url)

# 启动日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """offline 模式：只生成 SQL，不连数据库."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER TABLE 兼容
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """online 模式：直接连数据库执行迁移."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER TABLE 兼容
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
