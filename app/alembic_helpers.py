"""Alembic 迁移辅助：兼容 offline (--sql) 与 online 双模式.

offline 模式下 op.get_bind() 返回 MockConnection，不支持 inspect()；
本模块提供 get_inspector()，offline 时返回空结果对象，使存在性检查
自然走“对象不存在”分支，从而按原样生成 SQL。
"""

from alembic import context
from sqlalchemy import inspect


class _OfflineInspector:
    """offline 模式下假装所有对象都不存在."""

    def get_indexes(self, table_name):  # noqa: D401
        return []

    def get_columns(self, table_name):  # noqa: D401
        return []

    def get_table_names(self):  # noqa: D401
        return []


def get_inspector(bind):
    """返回兼容 offline/online 的 inspector.

    Args:
        bind: op.get_bind() 返回的连接对象。

    Returns:
        在线模式返回 sqlalchemy.inspect(bind)；offline 模式返回空结果包装器。
    """
    if context.is_offline_mode():
        return _OfflineInspector()
    return inspect(bind)
