"""应用配置模块.

采用 pydantic-settings 管理环境变量，提供统一的配置入口。

数据源策略（零预算纯免费路线）：
- 主源：worldcup26.ir（无需 key，已实测可用）
- 备份源：worldcupstats.football（爬虫）
- 兜底：手动录入（admin 后台）
- 已下线：API-Football、The Odds API（不订阅以保持零预算）
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置.

    Attributes:
        app_name: 应用名称。
        debug: 是否开启调试模式。
        database_url: SQLite 数据库 URL。
        admin_token: 管理员 Token，用于手动更新等敏感接口。
        sync_interval_seconds: 数据同步轮询间隔（秒）。
        worldcup26_base_url: worldcup26.ir API 根地址。
        worldcup26_timeout_seconds: worldcup26.ir 单次请求超时。
    """

    app_name: str = "2026 FIFA World Cup 赛事分析平台"
    debug: bool = True
    database_url: str = "sqlite:///./data/worldcup2026.db"
    admin_token: str = "change-me"

    # 同步配置
    sync_interval_seconds: int = 900  # 15 分钟轮询一次（零预算，避免被封）
    worldcup26_base_url: str = "https://worldcup26.ir"
    worldcup26_timeout_seconds: int = 20

    # v0.5.1: football-data.co 元数据接入（免费层，需注册 token）
    # 注册: https://www.football-data.org/  →  邮件激活 → 控制台取 token
    # 免费层限制: 10 req/min, 无赔率端点
    football_data_enabled: bool = False  # 默认关闭，避免无 key 时所有调用 401
    football_data_api_key: str = ""  # 主人需在 .env 填 FOOTBALL_DATA_API_KEY=<token>
    football_data_base_url: str = "https://api.football-data.org/v4"
    football_data_rate_limit_per_min: int = 10  # 免费层硬限制
    football_data_cache_ttl_seconds: int = 900  # 15min 内存缓存
    football_data_timeout_seconds: int = 20
    # v0.5.1: 6h 周期刷新配置(odds 快照打点 + fb-data 元数据)
    periodic_refresh_interval_hours: int = 6

    # 已下线配置（保留为占位字段，便于 .env 兼容）
    rapidapi_key: str = ""
    rapidapi_host: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
