"""应用配置模块.

采用 pydantic-settings 管理环境变量，提供统一的配置入口。

数据源策略（权威/稳定/低成本路线）：
- 权威规则：FIFA 官方规则 PDF / FIFA 官网（已本地化）
- 实时数据主源：API-Football 免费层（100 req/天，10 req/分）
- 实时数据备份：worldcup26.ir（无需 key）→ worldcupstats.football（爬虫）
- 低频元数据：football-data.org 免费层（需 token，默认关闭）
- 天气：Open-Meteo（免费，已接入）
- 赔率：The Odds API 免费层 / mock（默认 mock）
- 历史模型：StatsBomb Open Data + Hicruben（已接入）
- 兜底：手动录入（admin 后台）
"""

import logging
import os
from pathlib import Path

from pydantic import Field, AliasChoices, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)

# v0.13: 支持 DATA_DIR 环境变量，便于 Fly.io 等云平台的持久卷挂载
_DEFAULT_DATA_DIR = "./data"
_DATA_DIR = Path(os.environ.get("DATA_DIR", _DEFAULT_DATA_DIR))


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
        poisson_home_advantage: Elo→Poisson λ 主场优势偏移。
        poisson_base_lambda: Elo→Poisson λ 基础期望进球。
        poisson_goal_per_elo_diff: Elo 分差→λ 的每分进球系数。
        poisson_lambda_floor: λ 下限，避免极端差距时接近 0。
    """

    app_name: str = "2026 FIFA World Cup 赛事分析平台"
    debug: bool = False
    # v0.13: 数据库路径跟随 DATA_DIR，支持容器/云持久卷
    database_url: str = f"sqlite:///{_DATA_DIR}/worldcup2026.db"
    admin_token: str = ""

    # v0.14.3: CORS 安全配置；生产环境应通过 CORS_ORIGINS 设置为具体域名白名单
    # 使用 list[str] | str 是为了让 pydantic-settings 在环境变量解析失败时回退到原始字符串，
    # 再由 _parse_cors_origins 以逗号分隔解析为列表。
    cors_origins: list[str] | str = Field(
        default_factory=lambda: ["*"],
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins"),
    )
    cors_allow_credentials: bool = Field(
        default=False,
        validation_alias=AliasChoices("CORS_ALLOW_CREDENTIALS", "cors_allow_credentials"),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        """支持环境变量 CORS_ORIGINS 以逗号分隔传入多个域名."""
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    # 同步配置
    sync_interval_seconds: int = 900  # 15 分钟轮询一次（零预算，避免被封）
    # Fly secrets 脚本使用 WC26_BASE_URL,本地/文档使用 WORLDCUP26_BASE_URL,两者兼容
    worldcup26_base_url: str = Field(
        default="https://worldcup26.ir",
        validation_alias=AliasChoices("WORLDCUP26_BASE_URL", "WC26_BASE_URL"),
    )
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

    # v0.14.0: API-Football 实时数据主源（免费层，直接调用 api-sports.io）
    # 注册: https://www.api-football.com/ → 免费 tier 100 req/天
    api_football_enabled: bool = False  # 默认关闭，未配置 key 时自动回退 worldcup26.ir
    api_football_key: str = ""  # 在 .env 填 API_FOOTBALL_KEY=<your_key>
    api_football_host: str = "v3.football.api-sports.io"
    api_football_league_id: int = 1  # FIFA World Cup
    api_football_season: int = 2026
    api_football_rate_limit_per_min: int = 10  # 免费层 10 req/min
    api_football_daily_limit: int = 100  # 免费层 100 req/天
    api_football_cache_ttl_seconds: int = 900  # 15min 内存缓存
    api_football_timeout_seconds: int = 20

    # RapidAPI 代理模式（可选）。若配置 rapidapi_key，则 API-Football 通过 RapidAPI 调用；
    # 否则直接调用 api-sports.io。rapidapi_host 默认可空，为空时使用 api_football_host。
    rapidapi_key: str = ""
    rapidapi_host: str = ""

    # v0.7.2: 赔率 API 接入（零预算路线 + Mock 兜底）
    odds_api_enabled: bool = False  # 默认关闭,避免无 key 时所有调用 401
    odds_api_provider: str = "mock"  # mock | the_odds_api | pinnacle
    odds_api_key: str = ""  # 主人在 .env 填 ODDS_API_KEY=<token>
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_api_timeout_seconds: int = 20
    odds_api_rate_limit_per_min: int = 30
    # v0.7.2: 缓存 + 价值投注阈值
    odds_cache_ttl_seconds: int = 900  # 15min
    odds_value_bet_threshold: float = 0.05  # value_bet > 5% 视为强价值
    odds_default_bookmaker: str = "betpawa"  # 业界数据丰富 + 非洲市场覆盖好

    # v0.13.0: 6h 调度器自动拉取/更新赔率
    odds_auto_refresh_enabled: bool = True  # 是否在每个 6h 周期刷新时拉取赔率
    odds_fetch_look_ahead_days: int = 7  # 每次拉取未来多少天的比赛赔率

    # Elo→Poisson λ 参数（与 prediction.py / monte_carlo.py 统一，避免两处定义不一致）
    poisson_home_advantage: float = 60.0
    poisson_base_lambda: float = 1.35
    poisson_goal_per_elo_diff: float = 0.0035
    poisson_lambda_floor: float = 0.3

    # 时区策略：DB 统一存 UTC，API/前端统一按北京时间（Asia/Shanghai UTC+8）展示
    display_timezone: str = "Asia/Shanghai"

    # v0.14.2: 跳过 lifespan 启动时的全量同步/回填（生产部署稳定优先）
    # 默认 false：首次启动仍会自动同步。设为 true 后仅启动调度器，不触发外部请求。
    skip_startup_sync: bool = False

    @model_validator(mode="after")
    def _disable_mock_auto_refresh_in_production(self):
        """生产环境（debug=False）若使用 mock/seed 赔率且未配置 key，自动关闭定时刷新."""
        if (
            not self.debug
            and self.odds_api_provider in ("mock", "seed")
            and not self.odds_api_key
        ):
            if self.odds_auto_refresh_enabled:
                logger.warning(
                    "生产环境未配置真实赔率 API key，且 provider=%s，"
                    "已自动关闭 odds_auto_refresh_enabled，避免定时任务生成 mock 快照。"
                    "请在环境变量中设置 ODDS_API_KEY 与真实 provider。",
                    self.odds_api_provider,
                )
                self.odds_auto_refresh_enabled = False
        return self

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
