# 2026 FIFA World Cup 赛事分析平台 · 工程交付

> ## 🎛️ **v0.14.2 — Cockpit / 赛事总览驾驶舱去重 redesign（2026-06-17）**
> 将“总览”从“各板块内容的重复堆砌”重构为“统计 + 总预览 + 互联互通”：后端新增 `/api/cockpit/summary` 聚合赛事进度、晋级总览、数据源健康、未来 72h 关键战、模型共识、市场-模型分歧、Elo Top 5；前端 `renderCockpit` 重写为摘要/指标/关联入口，不再重复赛程/积分/赔率详情。
> 同步升级：Service Worker 缓存版本 `wc2026-v2`、静态资源加 `?v=0.14.2` 防旧版缓存、版本号改为显式常量 `0.14.2`、simulator 支持 `n_sims` 参数让总览模拟降到 1000 次以控制延迟。
> **494 passed, 1 skipped + 69 E2E 全绿**。
>
> ## 🛡️ **v0.14.1 — 数据质量校验层（去重 / 时效 / 状态机 / 优先级，2026-06-17）**
> 对 API-Football / worldcup26.ir 返回数据做“使用前分析”：按 key 去重、校验时间合理窗口、状态只允许 `scheduled → live → finished` 正向推进、低优先级源不覆盖高优先级源（manual > api-football > worldcup26.ir）。
> 多源编排器增加 `_api_football_quality_ok()`：重复率 >5% 或 not_found >50 时自动降级。
>
> ## 🌐 **v0.14.0 — 多源数据接入（API-Football + football-data.org，2026-06-17）**
> 主源 API-Football（api-sports.io 免费层 100 req/天），失败自动回退 worldcup26.ir；football-data.org 低频增强；未配置 key 时零成本走原备份路线。
> 新增 6h 全量 / 15min 实时 / 1h 积分榜调度、`ApiUsageLog` 预算监控、`/api/admin/sync/{full,live,status}` 管理端点。
>
> ## 🚀 **v0.13.0 — Fly.io 公网一键部署（2026-06-17）**
> 主人 3 真问题之 #1 部署/可用性 最后一公里. **fly.toml + deploy_fly.sh + fly_secrets_set.sh + migrate_data_to_fly.sh**.
> 设置 `FLY_API_TOKEN` 后执行 `./deploy_fly.sh`，自动获得 `https://wc2026-fifa-platform.fly.dev` HTTPS 入口 + 1GB 持久卷.
> 后续 hotfix: 赛事时间统一北京时间 (DB UTC / API+前端 +08:00)、数据完整性回归测试、`/health` version 动态读取 git tag.
>
> ## 🐳 **v0.12.0 — Deployment Infra 部署基础设施（2026-06-17）**
> 容器化 + CI 闭环. **Dockerfile + docker-compose.yml + .dockerignore + deploy.sh + .github/workflows/ci.yml**.
> 主人亦可自带 VPS (Ubuntu/Debian), 一行 `./deploy.sh` 拉最新代码 + 重 build + 启服务. CI push master 自动跑测试.
> v0.12.1 修复 ci.yml 中文冒号 YAML 解析 bug.
>
> ## 🎯 **v0.11.0 — Forward-Testing 真 forward 准确率（2026-06-17）**
> 直面主人 3 个真问题之 #2 真实准确率. prediction_log 加 is_live 字段区分 backfill vs live,
> `GET /api/elo/live-accuracy?is_live=true` + `GET /api/elo/live-window-accuracy?days=7` 两端点,
> Cockpit "🎯 真 Forward 准确率" mini-card 一眼看出赛前的真预测 vs 完赛结果. **6/17 距开赛 17 天, 端点返回 backfill_only (历史 1829 场, G2 62.7% / Elo 56.7%)**.
>
> **📡 v0.10.0 — Observability 观测能力落地（数据新鲜度追踪，2026-06-17）**
> 直面主人 3 个真问题之 #1 部署/可用性. scheduler 同步状态持久化 JSON, /health 暴露健康度,
> Cockpit "📡 数据新鲜度" widget 一眼看出 worldcup26.ir 同步是否健康.

> **文档版本**：v0.14.2（**Cockpit 去重 redesign 就绪** —— API-Football 主源 + worldcup26.ir 备份 + football-data.org 增强 + 多源回退 + 去重/时效/状态机/优先级保护 + 总览聚合 API，2026-06-17）
> **阶段**：Phase 5 – Ship ✅ **完成**（v0.7.x 模型演进 + 赔率深化 + 缓存 + Adaptive Weight + 数据回填 + 校准实验 4 版 + Cockpit 速览 + 校准 sunset 决策 + **v0.14 多源数据接入 + v0.14.1 数据质量校验层 + v0.14.2 Cockpit 去重 redesign**）
> **作用域**：48 强全量赛程 + **API-Football 实时主源** + worldcup26.ir 实时同步 + football-data.org 增强 + 多源回退 + Elo-Poisson v2 + **Glicko-2** + **ModelBlend (Elo + G2 加权)** + **Adaptive Weight (4 段按距上次比赛天数)** + **G2 校准（Platt + Isotonic 双方法，v0.8.1 已 sunset, 代码 git 保留）** + **Walk-forward 1226 场训练集（Hicruben 913 + StatsBomb 313）** + **StatsBomb 双数据源对比** + **Monte Carlo 10000 sims + 缓存层** + 出线模拟器 + Bracket 淘汰赛路线图 + **市场赔率模块 M3（管理员 + value bet + 走势 + 模型 vs 市场对比）** + 手动兜底 + CSV 导出 + 历史交锋详情页 + **准确率 dashboard** + **Cockpit 总览聚合 API `/api/cockpit/summary`**

---

## 一、范围与定位

### 1.1 范围（v0.5.0 已交付）

| 已交付 | 范围 |
|---|---|
| ✅ 静态 H5 前端（中文、深色） | 首页/赛程/积分榜/球队/比赛详情/Elo 实力榜/历史交锋/出线模拟器/Bracket 晋级路线图/赔率分析/准确率 dashboard；Tailwind + 移动优先；hash SPA |
| ✅ 后端 API（FastAPI · **67 端点**） | matches (4) / teams (3) / groups (1) / predictions (2) / elo (**19**,含 Glicko-2/Blend/Adaptive/Weight Sweep/Live Accuracy/已 sunset 的 calibration 410 端点) / h2h (2) / simulator (2) / bracket (1) / odds (**10+**) / weight-sweep (1) / admin (4) / admin_sync (**9**) / admin_odds (4) / health (1) + `/api/health/*` (3) |
| ✅ Elo-Poisson v2 预测 | M1 纯 Elo + Dixon-Coles + M2 增强（form + H2H 加权因子），双返回 v1/v2；v0.4.0 新增 StatsBomb 数据源切换 + Hicruben/StatsBomb 预测对比 |
| ✅ **Glicko-2 模型**（v0.6.0）| Python 原生实现（含 RD 衰减 + 12 期窗口 + vol/rating 同步更新），4 端点暴露 RD/σ/volatility + 1x2 胜率分布 + RPS/Brier/LogLoss 横评 |
| ✅ **ModelBlend (Elo + G2)**（v0.7.0a/b）| `w_elo + w_g2 = 1.0` 加权平均 + lifespan startup 自动写 prediction_log + `/#/elo` 3-tab UI（elo / glicko2 / blend）|
| ✅ **Adaptive Weight**（v0.7.5）| 按距上次比赛天数分 4 段 (FRESH ≤7d / WARM 7-30d / STALE 30-90d / DORMANT >90d) 动态调整 w_g2 |
| ✅ **G2 校准实验**（v0.7.8–v0.7.10，**v0.8.1 已关停**）| Platt scaling + Isotonic regression（PAVA 步阶）双方法对比 + `?method=platt|isotonic|both` Query 参数 + `calibration_metrics` 实测字段 + 进程内 6h cache + Cockpit mini-card 速览（Platt Full / Platt 80/20 / Isotonic 80/20 三列）。**结论**: brier 改进均 < 1.5pp 门槛, 端点返回 410, 详见 §九点六 顶部 banner |
| ✅ **市场赔率模块 M3+**（v0.5.0 → v0.7.2.3）| match_odds 表 + 6 端点（3 admin + 3 公开 + 3 model-compare + 1 service-status）+ value bet 算法 + 走势曲线 + 模型 vs 市场 + 按模型筛选价值投注 |
| ✅ **Monte Carlo 整届 10000 sims**（v0.7.1/1.1）| `MCRunHistory` 缓存层 + 6h warmup + `?refresh=1` 强制刷新 |
| ✅ **Weight Sweep**（v0.7.4）| 7 组 (w_elo, w_g2) walk-forward 验证，**G2 单独 (w_g2=1.0) brier 最低 0.5120** |
| ✅ **数据回填 v0.7.6** | StatsBomb 2018 WC 补 4 场 → 313 场 / 76 队 / 6 大赛 100% 覆盖 / 训练集扩到 1226 场 |
| ✅ 出线模拟器 | `/api/simulator/groups` + `/api/simulator/tournament`（MC 10000 sims）+ 前端交互式界面 |
| ✅ Bracket 淘汰赛路线图 | `/api/bracket` 自动计算 32 强（12 组前 2 + 8 个最佳第三）+ 16 场 R32 对阵 + Elo 胜率预测；`#/bracket` 真实数据渲染 + 15min 自动重算 |
| ✅ CSV 导出 | Elo 页 "导出 CSV" 按钮（48 队全榜 + 10 字段 + UTF-8 BOM）|
| ✅ 历史交锋详情页 | 路由 `#/h2h/{code1}/{code2}` + 视角归一 + 9 队非参赛队 fallback |
| ✅ 数据导入 | **API-Football 主源**（RapidAPI，免费 100 req/天，失败回退）+ worldcup26.ir 实时同步（每 15min 调度 + 启动时立即同步）+ worldcupstats.football 备份 + football-data.org 低频增强 + 手动兜底 + 赔率 admin 录入 |
| ✅ 赛事时间 | DB 统一存 UTC，API/前端统一按北京时间（`Asia/Shanghai`）展示；`/matches?date=` 与 `/matches/today` 按北京时间过滤 |
| ✅ 手动管理接口 | 16 端点（比分/事件/统计/Bracket 重建/同步触发/form 回填/H2H 回填/备份源调度/回测运行/赔率 3 端点），需 `X-Admin-Token` |
| ✅ 比赛详情 | events / stats / 赛后复盘卡片（B4）/ weather / **赔率卡（去 vig 市场概率 + 价值投注高亮）** |
| ✅ 自动化测试 | **494 项**单元 + 集成（实测：494 passed, 1 skipped）+ **69 项** Playwright E2E（实测：69 passed），全部通过 |

### 1.2 Non-Goals

- 实时 WebSocket 推送（v0.2 已下线，改用 15min 轮询 + lifespan startup 同步）
- 多语言切换（仅中文）
- 球员 360° 档案（v0.3+，需 Transfermarkt 集成）
- 投注 / 社区 PK（永不交付，平台不碰博彩）

---

## 二、架构与目录

```
worldcup2026-platform/
├── app/
│   ├── main.py              # FastAPI 入口（含 lifespan startup 同步）
│   ├── config.py            # pydantic-settings
│   ├── db.py                # SQLAlchemy engine / session
│   ├── models.py            # ORM（teams/stadiums/matches/events/stats/standings/api_usage_log/prediction_cache/team_elo_ratings/h2h_historical_matches/prediction_log/match_odds/odds_snapshots/mc_run_history）
│   ├── schemas.py           # Pydantic IO 模型
│   ├── routers/
│   │   ├── matches.py       # 4 端点
│   │   ├── teams.py         # 3 端点
│   │   ├── groups.py        # 1 端点
│   │   ├── predictions.py   # 2 端点
│   │   ├── elo.py           # 19 端点（Elo/Glicko-2/Blend/Adaptive/Accuracy/Weight Sweep）
│   │   ├── h2h.py           # 2 端点
│   │   ├── simulator.py     # 2 端点（groups/tournament）
│   │   ├── bracket.py       # 1 端点
│   │   ├── odds.py          # 10+ 端点
│   │   ├── health.py        # 3 端点
│   │   ├── cockpit.py       # 1 端点（总览聚合）
│   │   ├── admin.py         # 4 端点
│   │   ├── admin_sync.py    # 9 端点
│   │   └── admin_odds.py    # 4 端点
│   ├── services/
│   │   ├── bracket_logic.py # 2026 淘汰赛对阵生成
│   │   ├── prediction.py    # Elo-Poisson v1
│   │   ├── prediction_cache.py  # F2 缓存层
│   │   ├── prediction_log.py    # 预测日志 / 结算 / 准确率
│   │   ├── backtest.py      # B6 历史回测（111 场 H2H + 当前 FIFA 排名静态代理）
│   │   ├── elo.py           # Elo + Dixon-Coles + form/H2H 增强 + Blend
│   │   ├── statsbomb_elo.py # StatsBomb 双数据源
│   │   ├── glicko2.py       # Glicko-2 实现
│   │   ├── adaptive_weight.py # 自适应分段权重
│   │   ├── weight_sweep.py  # 权重扫描
│   │   ├── model_odds_compare.py # 模型 vs 赔率对比
│   │   ├── odds_service.py / odds_api_client.py / football_data.py / periodic_refresh.py # 赔率模块
│   │   ├── monte_carlo.py   # MC 整届模拟
│   │   ├── simulator.py     # 小组出线模拟
│   │   ├── h2h_backfill.py  # H2H 种子回填
│   │   ├── recent_form.py   # form 回填
│   │   ├── worldcup26_sync.py  # worldcup26.ir 同步
│   │   ├── sync_status.py   # 同步状态持久化
│   │   ├── data_source_health.py # 数据源健康
│   │   ├── data_quality.py  # 去重 / 时效 / 状态机 / 源优先级保护
│   │   ├── cockpit.py       # 总览驾驶舱聚合服务
│   │   └── scheduler.py     # APScheduler 调度
│   └── static/
│       ├── index.html       # H5 SPA 入口（抽屉 + 6 大模块路由）
│       ├── css/styles.css   # 自定义样式（Tailwind 互补）
│       └── js/app.js        # 路由 + 渲染（renderElo / renderH2H / renderH2HDetail / renderCockpit 等 12+ 函数）
├── data/
│   ├── scraper.py           # worldcupstats.football 抓取
│   ├── seed.py              # 原始 JSON → SQLite
│   ├── seed/
│   │   ├── h2h_seed.py      # 2018+2022 世界杯 111 场 H2H 种子
│   │   └── statsbomb/       # StatsBomb Elo 种子数据
│   ├── worldcup2026.db      # SQLite（git 忽略）
│   └── fixtures/            # 抓取的原始 JSON
├── tests/                    # 单元/集成测试（494+ 项）
│   ├── conftest.py
│   ├── test_api.py / test_api_integration.py / test_edge_cases.py
│   ├── test_elo.py / test_enhanced_elo.py / test_statsbomb_elo.py
│   ├── test_glicko2.py / test_model_blend.py / test_adaptive_weight.py
│   ├── test_monte_carlo.py / test_mc_cache.py / test_simulator.py
│   ├── test_bracket.py / test_h2h.py / test_prediction.py
│   ├── test_odds_*.py / test_admin_odds.py
│   ├── test_forward_testing.py / test_prediction_log*.py
│   ├── test_v012_deployment.py / test_v013_fly.py
│   └── e2e/                  # Playwright E2E 测试
├── scripts/                  # Playwright E2E + 训练/工具脚本
├── deliverables/             # 阶段交付报告
├── docs/screenshots/         # 截图归档
├── Dockerfile / docker-compose.yml / deploy.sh / fly.toml
├── .github/workflows/ci.yml  # GitHub Actions CI
├── requirements.txt
├── .env.example              # 本地配置示例
└── README.md
```

### 2.1 数据流

```
API-Football (primary, 免费层 100 req/天)
   ↓ /fixtures + /standings + /events + /teams
   ↓ 滑动窗口限速 10 req/min + 日预算守护
   ↓
api_football_sync.py ──→ SQLite (比分/状态/积分榜/事件)
                          ↑
                          │ 6h 全量同步 (periodic_refresh step 0)
                          │ 15min 轻量实时同步 (scheduler live_sync)
                          │
worldcup26.ir (backup, 无需 key)
   ↓ /get/teams + /get/stadiums + /get/games + /get/groups
   ↓ wc26_id → fifa_code 映射（修 ID 错位）
   ↓
worldcup26_sync.py ──→ SQLite (48 队 + 16 球场 + 104 比赛 + 48 standings)
                          ↑
worldcupstats.football (backup) ──→ scraper.py → fixtures/*.json → seed.py
                          ↑
football-data.org (enhance, 默认关闭)
   ↓ 10 req/min 免费层，需 FOOTBALL_DATA_API_KEY
   ↓
football_data.py ──→ 赛程/比分元数据交叉验证
                          ↑
StatsBomb Open Data ──→ scripts/download_statsbomb.py / build_statsbomb_from_extracted.py
   ↓ 313 场国际大赛 → train_statsbomb_elo() → data/seed/statsbomb/statsbomb_elo.json
   ↓（Hicruben 保持默认主模型；StatsBomb 作为可切换对比源）
Admin POST (X-Admin-Token) ──→ admin.py + admin_sync.py
                          ↓
                   FastAPI API (67 端点，含 /、/health、/api/cockpit/summary)
                          ↓
                   H5 SPA (app.js · 12+ 渲染函数 · hash 路由)
                          ↑
                   User (Web / Mobile 375px)
```

> **多源优先级**：API-Football（若启用）→ worldcup26.ir → worldcupstats.football → 手动兜底。\
> 未配置 `API_FOOTBALL_KEY` 时自动回退到原有 worldcup26.ir 路线，零 key 仍可用。

---

## 三、启动

### 3.1 安装

```bash
cd worldcup2026-platform
python -m pip install -r requirements.txt
```

### 3.2 导入种子数据

```bash
python data/scraper.py        # 抓取并保存到 data/fixtures/
python data/seed.py           # 写入 SQLite
```

### 3.3 启动 API

**推荐（Windows，避免 cwd 导致 SQLite 路径跑偏）**：

```bash
python scripts/start_server.py
```

或手动启动（务必先 `cd` 到项目根目录）：

```bash
cd worldcup2026-platform
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> ⚠️ `--app-dir` 只改 `sys.path`，**不会改进程 cwd**。若从项目外启动，相对路径 `data/worldcup2026.db` 会指向错误位置。

访问：

- H5 首页：<http://127.0.0.1:8000/>
- 健康检查：<http://127.0.0.1:8000/health>
- API 文档（仅 debug=true）：<http://127.0.0.1:8000/api/docs>

### 3.4 测试

```bash
python -m pytest tests/ -v
```

---

## 四、环境变量

`.env` 示例（完整版见 `.env.example`）：

```ini
ADMIN_TOKEN=worldcup2026-admin
APP_NAME=2026 FIFA World Cup 赛事分析平台
DEBUG=true
DATABASE_URL=sqlite:///./data/worldcup2026.db
DATA_DIR=./data

# 数据同步
SYNC_INTERVAL_SECONDS=900
WC26_BASE_URL=https://worldcup26.ir

# 核心数据：API-Football（api-sports.io / RapidAPI）。未配置 key 时自动回退 worldcup26.ir。
API_FOOTBALL_ENABLED=false
API_FOOTBALL_KEY=YOUR_APISPORTS_KEY
API_FOOTBALL_HOST=v3.football.api-sports.io
API_FOOTBALL_LEAGUE_ID=1
API_FOOTBALL_SEASON=2026
API_FOOTBALL_DAILY_LIMIT=100
API_FOOTBALL_RATE_LIMIT_PER_MIN=10

# 增强数据源：football-data.org（可选，留空则关闭）
FOOTBALL_DATA_ENABLED=false
FOOTBALL_DATA_API_KEY=
FOOTBALL_DATA_BASE_URL=https://api.football-data.org/v4

# 赔率 API（零预算可保持 mock）
ODDS_API_ENABLED=false
ODDS_API_PROVIDER=mock
ODDS_API_KEY=
```

> ⚠️ 生产部署务必修改 `ADMIN_TOKEN` 与 `DEBUG=false`。

---

## 五、部署（二选一）

### 5.1 推荐：Fly.io 一键部署

适合不想维护 VPS 的主人，免费 tier 含 1GB 持久卷 + 自动 HTTPS。

```bash
# 1. 安装 flyctl 并获取 token
#    https://fly.io/docs/hands-on/install-flyctl/
export FLY_API_TOKEN=<your-token>

# 2. 部署
./deploy_fly.sh

# 3. 注入 secrets（ADMIN_TOKEN 必填）
./fly_secrets_set.sh

# 4. （可选）把本地已有数据上传到 Fly
./migrate_data_to_fly.sh
```

部署成功后：
- 健康检查：`https://wc2026-fifa-platform.fly.dev/health`
- 管理面板：`https://wc2026-fifa-platform.fly.dev/#/cockpit`

### 5.2 自托管：Docker + VPS

适合已有服务器/域名的主人。

```bash
# 1. 复制环境变量
# 2. 运行一键部署脚本
./deploy.sh
```

脚本会执行 `git pull → docker compose build --no-cache → up -d → 60s /health 轮询`。
HTTPS / 域名需主人自行配置（如 certbot + nginx）。

---

## 六、Schema 迁移（Alembic）

项目使用 [Alembic](https://alembic.sqlalchemy.org/) 管理所有 schema 演进。

```bash
# 应用最新迁移
alembic upgrade head

# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 回滚一步
alembic downgrade -1

# 自动生成新迁移（修改 app/models.py 后）
alembic revision --autogenerate -m "改了什么"
```

**当前迁移链**（共 13 个）：
1. `aeaf6e483292` — init baseline（基线 + 补缺失索引）
2. `d7d93b3ec71e` — F2 `prediction_cache.factors_breakdown`
3. `ae0ea4ea9892` — M1 `team_elo_ratings` 表
4. `b1c5e7f9a2d3` — M3 `match_odds` 表
5. `b9c4d8e2f1a3` — v0.5.1 `odds_snapshots` 表
6. `c3e8b5f2a9d1` — v0.6.0 `prediction_log` 表
7. `e916a40edd77` — v0.7.1.1 `mc_run_history` 表
8. `f3a9b2c1d4e6` — v0.8.1 清理 calibration 模型行
9. `k2l5m8n3p7q9` — v0.11 `prediction_log` 加 `is_live` / `snapshot_group`
10. `ccd9db6f49a1` — v0.13 补 `prediction_log.is_live` 索引
11. `e1bc3cd68e68` — v0.13 清理孤儿表 `odds_api_cache`
12. `6faeb80b20c2` — 在 `stadiums.name_en` 上加唯一约束
13. `434e91a025fa` — 将 `matches.kickoff` 转换为 UTC

详细报告见 [`deliverables/T1_alembic_completion_report.md`](deliverables/T1_alembic_completion_report.md)。

---

## 六、API 速查（v0.14.2 共 67 端点，含 `/`、`/health`、`/api/*`）

> 完整交互式文档：`DEBUG=true` 时访问 `/api/docs` 或 `/api/redoc`。

### 6.1 核心数据 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 H5 SPA 首页 |
| GET | `/health` | 健康检查 + 版本 + DB 行数 + 同步状态 + scheduler 状态 |
| GET | `/api/health/sources` | 各数据源健康度（worldcup26/football-data/odds-api 等）|
| GET | `/api/health/sources/{source_id}` | 单数据源健康详情 |
| GET | `/api/health/sync-status` | 同步状态详情 |
| GET | `/api/cockpit/summary` | **总览驾驶舱聚合摘要**（进度/晋级/健康/关键战/共识/分歧/Elo Top 5）|
| GET | `/api/matches` | 全部比赛，支持 `?date=&group=&status=` |
| GET | `/api/matches/today` | 今日比赛（北京时间），进行中置顶 |
| GET | `/api/matches/{id}` | 单场详情（events/stats/赔率卡/赛后复盘）|
| GET | `/api/matches/{id}/weather` | 比赛天气（Open-Meteo）|
| GET | `/api/matches/{id}/prediction` | Elo-Poisson v1 预测 |
| GET | `/api/matches/{id}/odds` | 单场赔率 + consensus + 去 vig 市场概率 |
| GET | `/api/matches/{id}/odds/history` | 赔率时间序列（多公司多时间点）|
| GET | `/api/teams` | 球队列表 |
| GET | `/api/teams/{team_code}` | 球队详情（兼容 int ID / FIFA 3 字母代码，大小写不敏感）|
| GET | `/api/teams/{team_code}/matches` | 球队赛程 |
| GET | `/api/teams/{team_code}/h2h-opponents` | 该队所有历史交锋对手 |
| GET | `/api/groups` | 12 小组积分榜 |

### 6.2 Bracket + 模拟器 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bracket` | 完整淘汰赛对阵树（R32→Final）+ Elo 预测 |
| POST | `/api/admin/bracket/rebuild` | 手动触发 Bracket 重算并持久化 |
| GET | `/api/simulator/groups` | 小组出线模拟 |
| GET | `/api/simulator/tournament` | 整届 Monte Carlo 10000 sims |

### 6.3 Elo / Glicko-2 / Blend / Adaptive 预测 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/elo/ratings?source=hicruben\|statsbomb` | Elo 评分全榜 |
| GET | `/api/elo/ratings/{fifa_code}?source=...` | 单队评分 |
| GET | `/api/elo/top?limit=&source=...` | Top N |
| GET | `/api/elo/predict/{home}/{away}?source=&match_id=` | 1v1 预测（v1）|
| GET | `/api/elo/predict-enhanced/{home}/{away}?source=...` | v1 + v2（form + H2H）|
| GET | `/api/elo/compare/{home}/{away}` | Hicruben vs StatsBomb 并排对比 |
| GET | `/api/elo/backtest` | 回测指标（读预生成 metrics）|
| GET | `/api/elo/predict-glicko2/{home}/{away}` | Glicko-2 1v1 预测 |
| GET | `/api/elo/glicko2-ratings` | Glicko-2 全队评分 |
| GET | `/api/elo/glicko2-metrics` | Glicko-2 训练指标 |
| GET | `/api/elo/predict-blend/{home}/{away}?w_elo=&w_glicko2=` | Elo + G2 融合预测 |
| GET | `/api/elo/accuracy-stats` | 已结算预测准确率统计 |
| GET | `/api/elo/live-accuracy?is_live=&model_version=` | 真 forward 准确率 |
| GET | `/api/elo/live-window-accuracy?days=&model=` | N 天窗口真准确率 |
| GET | `/api/elo/top-bias` |  Top 预测偏差分析 |
| GET | `/api/elo/weight-sweep` | 7 组权重扫描 |
| GET | `/api/elo/adaptive-weight/{home}/{away}` | 自适应分段权重预测 |
| POST | `/api/elo/predict-market-blend` | Elo 与市场赔率混合预测（接收 `{home_team, away_team, market_home_win, market_draw, market_away_win}`） |
| GET | `/api/elo/calibrated-predict/{home}/{away}` | **已 sunset (410 Gone)** |
| GET | `/api/elo/calibration-summary` | **已 sunset (410 Gone)** |
| GET | `/api/h2h/{code1}/{code2}` | 两队历史交锋（视角归一）|
| GET | `/api/predictions/cache/stats` | 预测缓存统计 |

### 6.4 赔率 API（v0.5.0 → v0.7.2）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/odds/compare?min_rate=` | 所有未完赛：赔率 vs Elo + value bet |
| GET | `/api/odds/value-bets?min_rate=&limit=` | 价值投注 TOP N |
| GET | `/api/odds/latest` | 返回所有比赛的最新赔率摘要（支持 `?match_id=` 过滤） |
| GET | `/api/odds/compare-model?match_id=&model=&bookmaker=` | 单场比赛：模型 vs 赔率（model: blend/elo/glicko2）|
| GET | `/api/odds/value-bets-model?model=&min_tier=` | 按模型筛选价值投注 |
| GET | `/api/odds/service-status` | 赔率服务状态 |
| GET | `/api/odds/{match_id}/history-comparison` | 赔率 vs 模型概率走势 |
| POST | `/api/admin/odds` | 手动录入单条赔率 |
| POST | `/api/admin/odds/batch` | 批量录入赔率 |
| POST | `/api/admin/odds/fetch` | 手动触发 fetch + upsert |
| DELETE | `/api/admin/odds/{odds_id}` | 删除单条赔率 |

### 6.5 管理 API（需 `X-Admin-Token`）

**6.5.1 数据手动维护**（前缀 `/api/admin/`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/admin/matches/{id}/score` | 手动更新比分 |
| POST | `/api/admin/matches/{id}/events` | 手动录入事件 |
| POST | `/api/admin/matches/{id}/stats` | 手动录入赛后统计 |
| POST | `/api/admin/bracket/rebuild` | 手动触发 Bracket 重算 |
| POST | `/api/admin/odds` | 手动录入单条赔率 |
| POST | `/api/admin/odds/batch` | 批量录入赔率 |
| DELETE | `/api/admin/odds/{odds_id}` | 删除单条赔率 |

**6.5.2 数据同步 + 缓存**（前缀 `/api/admin/sync/`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/sync/status` | 同步状态与数据源配置 |
| POST | `/api/admin/sync/sync/full` | 触发多源编排全量刷新（API-Football → worldcup26.ir → 备份） |
| POST | `/api/admin/sync/sync/live` | 触发多源编排轻量实时同步（比分/状态/积分榜） |
| POST | `/api/admin/sync/worldcup26/full` | 触发 worldcup26.ir 全量同步（兼容旧端点） |
| POST | `/api/admin/sync/recent-form/backfill` | 触发 recent_form 回填 |
| POST | `/api/admin/sync/stadium-coords/fill` | 补球场经纬度 |
| POST | `/api/admin/sync/h2h/backfill` | 触发 H2H 种子回填 |
| POST | `/api/admin/sync/worldcupstats/schedule` | 触发备份源抓取 |
| POST | `/api/admin/sync/backtest/run` | 触发 B6 回测（111 场 H2H 历史种子 + 当前 FIFA 排名代理）|

### 6.6 手动更新示例

```bash
curl -X POST -H "X-Admin-Token: worldcup2026-admin" \
  -H "Content-Type: application/json" \
  -d '{"home_score":2,"away_score":1,"status":"finished","time_elapsed":"90"}' \
  http://127.0.0.1:8000/api/admin/matches/1/score
```

---

## 七、预测模型 v0（Elo-Poisson）

### 6.1 公式

```
λ_home = BASE_LAMBDA + (Elo_home - Elo_away + 60) × 0.0035
λ_away = BASE_LAMBDA - (Elo_home - Elo_away + 60) × 0.0035
λ_min = 0.3

P(i:j) = Poisson(λ_home, i) × Poisson(λ_away, j)
P(home_win) = Σ P(i:j) for i > j
P(draw)     = Σ P(i:j) for i == j
P(away_win) = Σ P(i:j) for i < j
```

### 6.2 局限性（明确声明）

- 无近期状态、无阵容、无伤停、无历史交锋
- Elo 为手工分层（强队 1850 / 中上 1700 / 中游 1600 / 其余 1500）
- 进球期望 BASE_LAMBDA = 1.35
- 仅用于首版 MVP，v0.2 引入 xG / 阵容 / 伤停

### 6.3 替代模型候选

- 蒙特卡洛模拟（出线概率，v0.3）
- Dixon-Coles 低分修正（比分分布更准）
- Gradient Boosting（吃更多特征）

---

## 七·B、Elo 评级系统（M1 · 4 年真实数据驱动）

**数据源**：`Hicruben/world-cup-2026-prediction-model` (32 stars) — 913 场真实国际赛（2023-11 ~ 2026-06）+ 60+ 队 Elo 评分。完整绕过 FIFA 反爬。

**模型**：Elo（K=60, home_bonus=70）+ Dixon-Coles bivariate Poisson（ρ=-0.13）。

**离线 4 年 walk-forward 回测**（`scripts/m1_backtest.py`，burn-in 150 场 + 评估 763 场）：

| 指标 | 我们的实现 | 投币基线 | 提升 |
|------|------------|----------|------|
| Ranked Probability Score (↓) | **0.2002** | 0.241 | **-17%** |
| Log-loss (↓) | **0.9690** | 1.10 | **-12%** |
| Brier score (↓) | **0.5752** | 0.67 | **-14%** |
| 准确率 (↑) | **58.3%** | 33% | **+77%** |
| 期望校准误差 | 11.75% | - | （10 段分箱偏粗） |

> ⚠️ 注意：平台内置回测引擎 `app/services/backtest.py`（`/api/admin/sync/backtest/run`）与上述离线回测不同。它使用 2018+2022 世界杯 **111 场 H2H 历史种子**和**当前 FIFA 排名静态代理**，仅验证模型对历史大赛的校准度，不重复 913 场 walk-forward。

**48 队 Elo 评分 Top 10**：ESP 2010 / FRA 2009 / ENG 1993 / ARG 1976 / BRA 1955 / POR 1945 / GER 1926 / ITA 1901 / NED 1894 / NOR 1880

**5 个新 API 端点**：

```bash
GET /api/elo/ratings                  # 48 队评分
GET /api/elo/ratings/{FIFA}           # 单队评分
GET /api/elo/predict/{home}/{away}    # 1v1 预测
GET /api/elo/top?limit=10             # Top N
GET /api/elo/backtest                 # 离线 4 年回测指标（预生成）
```

**示例**（ESP vs HAI）：

```json
{
  "home": {"fifa_code": "ESP", "elo": 2010},
  "away": {"fifa_code": "HAI", "elo": 1537},
  "probabilities": {"home_win": 0.871, "draw": 0.109, "away_win": 0.020},
  "expected_goals": {"home": 2.71, "away": 0.3}
}
```

详见 `deliverables/M1_elo_completion_report.md`。

## 七·C、Elo 前端页（M1.5 · 1v1 对比器 + 48 队全榜）

**入口**：抽屉 "📈 Elo 实力榜"（M1 角标），或直接访问 `/#/elo`。

**4 大区块**：
1. **顶栏 + 4 KPI 卡**：63 队 / Top 1 (ESP 2010) / 强弱差 (594) / 回测准确率 (58.3%)
2. **1v1 对比器**：两个 select + 实时调 `/api/elo/predict/{h}/{a}`，三色概率条 + 期望进球 + 智能结论
3. **48 队 Elo 全榜**：排名 + 国旗 + 队名 + 小组标签 + 实力分进度条（0-100） + 近 5 场得分
4. **回测指标卡片**：5 指标 (准确率/RPS/Log-loss/Brier/ECE) + 4 参数 + 数据范围 + 数据源

**截图归档**：`docs/screenshots/M1.5/` (4 张，PC 1440 + 移动 375)

详见 `deliverables/M1.5_elo_ui_completion_report.md`。

## 七·D、M2 增强 Elo 预测（Elo + form + H2H）

**核心**：在 M1 纯 Elo 基础上加入 form（近期状态）和 H2H（历史交锋）加权因子，**不破坏 M1**。

**新端点**：

```bash
GET /api/elo/predict-enhanced/{home}/{away}  # v1 + v2 双返回
```

**核心公式**（service 纯函数）：

```python
form_boost  = (recent_form_points - 7.5) * 5    # 0 → -37.5, 15 → +37.5
h2h_boost   = (home_win_rate - 0.5) * 50          # 0% → -25, 100% → +25
effective_elo = base_elo + form_boost + h2h_boost
```

**数据基础（诚实交代）**：

| 因子 | 覆盖 | 实际效果 |
|---|---|---|
| form | 48 队中 **4 队** (MEX/KOR/RSA/CZE) | ✅ 生效 |
| H2H | 14 对决有 ≥ 2 场样本 | ❌ 几乎全部 50/50 → boost=0 |

**案例**：MEX vs CZE 主胜 v1 63.67% → v2 65.41%（form 生效）

**未做**：walk-forward 回测（数据时间跨度不匹配 Hicruben 913 场）

详见 `deliverables/M2_enhanced_elo_completion_report.md`。

---

## 七·E、P1.2 Elo CSV 导出（前端 Blob 下载）

**核心**：Elo 页 header 加"📥 导出 CSV"按钮，**纯前端**触发浏览器下载 63 队 Elo 全榜。

**触发流程**：

```
点击按钮 → 拉 /elo/ratings + /teams?limit=48 → client-side join
→ 算实力分（锚定 1400 参考线） → 加 UTF-8 BOM → Blob(text/csv)
→ URL.createObjectURL + a.download → 浏览器下载
→ 按钮自我反馈 "✅ 已导出 63 队"（2 秒后恢复）
```

**字段（10 列）**：

| 列 | 字段 | 来源 |
|---|---|---|
| 1 | 排名 | 计算（按 Elo 降序） |
| 2 | FIFA 代码 | /elo/ratings |
| 3 | 中文名 | /teams |
| 4 | 英文名 | /teams |
| 5 | 小组 | /teams |
| 6 | 国旗 | /teams |
| 7 | Elo 评分 | /elo/ratings |
| 8 | 实力分 (0-100) | 计算：`(elo-1400)/(topElo-1400)*100` |
| 9 | 近 5 场得分 | /teams |
| 10 | 近 5 场净胜 | /teams |

**文件名**：`wc2026_elo_ratings_YYYY-MM-DD.csv`（日期戳）

**关键技术**：

- **UTF-8 BOM** (`\uFEFF`)：让 Excel 中文版正确识别 UTF-8
- **CRLF 行结束符**：RFC 4180 标准
- **RFC 4180 转义**：含 `,` / `"` / `\r` / `\n` 的字段加双引号，内部 `"` → `""`
- **按钮自我反馈**：无 toast 基础设施时用 `className` 操作

**验证**：

- Playwright：`scripts/p1_2_test_export.py`（点按钮 → 抓下载 → 验内容）
- 95/95 测试全过（**零回归**，仅前端新增）
- 移动端 375px 按钮位置 x=235 y=82 在视口内

**输出样例**（首 4 行）：

```csv
排名,FIFA代码,中文名,英文名,小组,国旗,Elo评分,实力分(0-100),近5场得分,近5场净胜
1,ESP,西班牙,Spain,H,🇪🇸,2010,100.0,,
2,FRA,法国,France,I,🇫🇷,2009,99.8,,
3,ENG,英格兰,England,L,🏴󠁧󠁢󠁥󠁮󠁧󠁿,1993,97.2,,
```

详见 `deliverables/P1.2_data_export_completion_report.md`。

---

## 七·F、P1.3 历史交锋详情页（两队完整对决 · 视角归一）

**核心问题**：match detail 页"⚔️ 历史交锋"卡片**只显示胜负条**（1胜1平0负），
看不到具体场次。用户想看两队**完整历史交锋**（2018+2022 世界杯 + 2026 完赛）。

**触发流程**：

```
match detail → 点 "📜 完整历史 →" 链接
  → 跳转到 #/h2h/{code1}/{code2}
  → 调 GET /api/h2h/{code1}/{code2}
  → 渲染：胜负条 + 完整场次列表（按日期倒序）
```

**端点**：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/h2h/{code1}/{code2}` | 两队所有直接对决 + 胜负条 |
| GET | `/api/teams/{code}/h2h-opponents` | 该队所有历史交锋对手（留 #P2 用） |

**前端**：新路由 `#/h2h/{code1}/{code2}` + `renderH2HDetail()` 函数 + 头部胜负条 + 场次卡片

**关键技术 — 视角归一**：

`_normalize_match()` 函数把任意主客方向的比赛归一为 code1 视角：

```python
if raw_home_code == code1:
    code1_score, code2_score = raw_home_score, raw_away_score
    is_code1_home = True
else:
    code1_score, code2_score = raw_away_score, raw_home_score  # 翻转
    is_code1_home = False
```

**验证案例**（视角翻转正确）：

| 端点 | 视角 | 2022 决赛 (原 ARG 3-3 FRA · ARG 主场) | 2018 16强 (原 FRA 4-3 ARG · FRA 主场) |
|---|---|---|---|
| `/api/h2h/ARG/FRA` | code1=ARG | 平局 3-3 | code1 输 3-4 → 0胜1平1负 |
| `/api/h2h/FRA/ARG` | code1=FRA | 平局 3-3 | code1 赢 4-3 → **1胜1平0负** ✓ |

**Match 模型字段踩坑**（修复 2 个 AttributeError）：

| Bug | 原因 | 修复 |
|---|---|---|
| `'Match' has no attribute 'match_date'` | Match 表用 `kickoff_at`（H2H 表才用 match_date） | 改用 `m.kickoff_at` |
| `'Match' has no attribute 'competition'` | Match 表无 competition 字段 | 写死 `"2026 FIFA World Cup"`，stage fallback `Group {group_name}` |

**数据基础**：
- H2HHistoricalMatch 表：**111 场**（2018+2022 世界杯种子，涉及 39 支队）
- 2026 已完赛：MEX vs RSA + KOR vs CZE（2 场）
- 总对决组合：~100 对（code1/code2 互换计 2 次）

**验证**：
- Playwright `scripts/p1_3_test_h2h.py`：**6/6 通过**
  - 路由可达 + 数据正确 / 空态 / 2026 完赛 / match detail 入口 / 移动端 / API 边界
- 后端 `pytest tests/`：**95/95 passed**（零回归）
- 5 张截图归档 `docs/screenshots/P1.3/`

**Playwright 选择器踩坑**（值得记入 future session）：

`page.locator("a[href='#/h2h/MEX/RSA']")` 失败！原因是 `#` + `/` 在 CSS selector 里被特殊解析，
会跟 `fragment` 冲突。**修法**：用 attribute partial match `"a[href*='h2h/MEX']"`。

---

## 七·G、v0.4.0 StatsBomb Elo 双数据源（对比源，非替代）

**背景**：评估后发现 StatsBomb Open Data 国际大赛覆盖仅 **~309 场**（世界杯 2018/2022、欧洲杯 2020/2024、美洲杯 2024、非洲杯 2023），约为 Hicruben 913 场的 34%；且缺少 2023-2026 友谊赛/预选赛/国家联赛，**至少 8 支 2026 参赛队无数据**（IRQ、UZB、JOR、NZL、BIH、CUW、HAI、NOR）。因此 StatsBomb **不替代 Hicruben**，而是作为可切换对比数据源。

**实现**：

1. **训练模块** `app/services/statsbomb_elo.py`
   - 下载/解析 StatsBomb Open Data JSON（或离线 compact 格式）
   - 球队名 → FIFA 3 字母代码映射（`Cape Verde Islands`→CPV、`Congo DR`→COD 等）
   - 中性场地 `home_bonus=0` 训练 Elo（K=60），输出 `data/seed/statsbomb/statsbomb_elo.json`
   - 离线构建脚本：`scripts/build_statsbomb_from_extracted.py`（309 场）
   - 在线构建脚本：`scripts/download_statsbomb.py`（有外网环境时使用）

2. **服务层 source 参数** `app/services/elo.py`
   - `predict_match(..., source="hicruben")` / `predict_match_enhanced(..., source="hicruben")`
   - `get_top_elo(..., source="hicruben")` / `get_elo_ratings(..., source="hicruben")`
   - StatsBomb 缺失球队自动 fallback 到 Hicruben，并在响应中标记 `rating_source="hicruben_fallback"` 与 `fallback_reason`

3. **API 层** `app/routers/elo.py`
   - 所有 `/api/elo/*` 端点支持 `?source=hicruben|statsbomb`
   - 新增 `GET /api/elo/compare/{home}/{away}`：同一对阵的 Hicruben vs StatsBomb 预测并排返回

4. **前端** `app/static/js/app.js`
   - Elo 页面顶部增加「Hicruben 默认」/「StatsBomb 对比」切换按钮
   - 1v1 预测器、Top N、CSV 导出均跟随当前 source
   - 切换 StatsBomb 时显示数据来源说明与 8 队 fallback 提示

**数据基础（诚实交代）**：

| 指标 | Hicruben | StatsBomb |
|---|---|---|
| 比赛场次 | 913 | 309 |
| 时间跨度 | 2023-11 ~ 2026-06 | 2018 ~ 2024 |
| 覆盖 2026 参赛队 | 48/48 | 40/48（8 队 fallback）|
| 场地处理 | home_bonus=70 | home_bonus=0（大赛中性场地）|
| 默认数据源 | ✅ 是 | ❌ 否（对比源）|

**Top 5 对比**（2026-06-15）：

| 排名 | Hicruben | StatsBomb |
|---|---|---|
| 1 | ESP 2010 | ESP 1733 |
| 2 | FRA 2009 | ARG 1676 |
| 3 | ENG 1993 | FRA 1655 |
| 4 | ARG 1976 | ENG 1646 |
| 5 | BRA 1955 | COL 1616 |

**验证**：

- `tests/test_statsbomb_elo.py`：**16/16 通过**
- 全量 `pytest tests/`：**152 passed, 1 skipped**
- Playwright E2E：`tests/e2e/test_spa_pages.py` **7/7 通过**
- 许可证：`data/seed/statsbomb/attribution.md` 按要求标注 StatsBomb 版权与 logo 使用声明

详见 `deliverables/v0.4.0_statsbomb_elo_completion_report.md`。

---

## 七·H、v0.5.0 市场赔率模块 M3（市场预期 vs Elo 模型对比）

### 1. 设计目标

为比赛引入"市场预期"（博彩公司隐含概率）这一第三方视角，与 Elo 模型预测对比，识别**价值投注机会**（value bet = 模型概率被市场低估）。

> ⚠️ 重要声明：本模块仅供分析参考，**不构成投注建议**。赔率数据由管理员手动录入（v0.5.0），未来 v0.5.1+ 可接入 football-data.co / The Odds API。

### 2. 数据模型

```sql
CREATE TABLE match_odds (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL,  -- FK matches.id
    bookmaker VARCHAR(50),       -- bet365/pinnacle/avg_market
    home_win FLOAT,              -- decimal 欧式赔率（1.01 ~ 1000.0）
    draw FLOAT,
    away_win FLOAT,
    over_2_5 FLOAT,
    under_2_5 FLOAT,
    fetched_at DATETIME,
    source VARCHAR(20) DEFAULT 'manual'  -- manual/history/api
);
CREATE INDEX idx_match_odds_match_id ON match_odds(match_id);
```

**关键设计**：
- 同 `match_id + bookmaker` **覆盖式更新**（同一博彩公司多次刷新只保留最新）
- 多家公司并行存在 → `consensus` 取平均
- 赔率范围 `[1.01, 1000.0]` 校验

### 3. 核心算法

```python
# 1. decimal 赔率 → 隐含概率（去 vig 前）
decimal_to_implied_prob(2.10) == 0.4762  # 47.62%

# 2. 归一化消除博彩公司利润（vig）
remove_vig([0.5, 0.3, 0.24])  # sum=1.04 → [0.481, 0.288, 0.231]，sum=1.0

# 3. 价值投注率
value_bet(model_prob=0.55, market_prob=0.48) == 0.146  # +14.6%
# > +5%:  强价值，理论上值得投注
# 0 ~ +5%: 边缘价值
# < 0:    模型认为被高估
```

参考：Kelly Criterion (1956) · "Trading Bases" by Joe Peta · Dixon-Coles (1997)

### 4. API 端点（v0.5.0 新增 6 个）

| 端点 | 用途 | 鉴权 |
|---|---|---|
| `POST /api/admin/odds` | 单条录入（覆盖式） | X-Admin-Token |
| `POST /api/admin/odds/batch` | 批量录入（含失败明细） | X-Admin-Token |
| `DELETE /api/admin/odds/{id}` | 删除单条 | X-Admin-Token |
| `GET /api/matches/{id}/odds` | 单场赔率 + consensus + 去 vig 市场概率 | 公开 |
| `GET /api/odds/compare` | 所有未完赛比赛：赔率 vs Elo + value bet | 公开 |
| `GET /api/odds/value-bets?min_rate=0.05` | 价值投注 TOP N（按 rate 降序）| 公开 |

### 5. 前端接入（3 处）

1. **matchCard 底部**（首页/赛程/球队详情/今日比赛）：小型赔率角标（主/平/客 1X2 赔率）
2. **match detail 页**：完整赔率卡片（各家赔率 + consensus + 市场概率 + vig 透明度）
3. **`/#/odds` 独立页面**：所有未完赛比赛赔率 vs Elo 对比 + 价值投注 TOP 5 高亮（amber 色）

### 6. 数据来源策略

| 来源 | 用途 | 状态 |
|---|---|---|
| Admin 手动录入 | 主路径（v0.5.0） | ✅ 已实现 |
| 历史回测赔率 | 用于回测 Elo vs 市场历史胜率 | 🔜 v0.5.1 |
| football-data.co API | 2026 实时赔率（免费层 10 req/min） | 🔜 v0.5.1 |
| The Odds API | 高级赔率源（500 req/月免费） | ❌ 不接入（零预算） |

### 7. 验证（41 + 4 测试全过）

- `tests/test_odds_service.py`：**18/18 通过**（归一化/vig/value_bet/aggregate 边界）
- `tests/test_admin_odds.py`：**13/13 通过**（鉴权/覆盖/批量/删除/无效赔率）
- `tests/test_odds_api.py`：**10/10 通过**（单场/对比/价值投注/limit/min_rate）
- 全量 `pytest tests/`：**193 passed, 1 skipped**（零回归）
- Playwright E2E `tests/e2e/test_odds.py`：**4/4 通过**（页面/抽屉入口/详情卡/375px 移动端）

### 8. 不做的事（scope 纪律）

- ❌ 实时推送（SSE/WebSocket）
- ❌ VIP 赔率源（Pinnacle 收费 API）
- ❌ 赔率走势图表（v0.5.1）
- ❌ 不修改 Elo 模型（独立模块，零侵入）

详见 `deliverables/v0.5.0_odds_completion_report.md`。

---

## 七·I、v0.5.1 赔率走势图表 + football-data.co 接入 + 6h 周期刷新

### 1. 设计目标

在 v0.5.0 静态赔率基础上,补齐三件事:
1. **赔率时间序列** —— 用 snapshot 表记录每次赔率变化,前端 Chart.js 折线图可视化
2. **football-data.co 元数据源** —— 备用交叉验证(免费层 10 req/min,需 token)
3. **6h 周期刷新** —— 自动给现有赔率打 snapshot,长跑后走势曲线自动丰富

### 2. 数据模型:odds_snapshots

```sql
CREATE TABLE odds_snapshots (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL,     -- FK matches.id
    bookmaker VARCHAR(50),
    home_win / draw / away_win FLOAT,
    over_2_5 / under_2_5 FLOAT,
    snapshot_at DATETIME NOT NULL,  -- 时间锚点(走势曲线 X 轴)
    source VARCHAR(20)              -- snapshot / manual / api
);
-- 复合索引:走势查询主索引
CREATE INDEX ix_odds_snap_match_book_time
    ON odds_snapshots(match_id, bookmaker, snapshot_at);
```

**种子迁移**(`b9c4d8e2f1a3`)：v0.5.0 的 9 条 seed 赔率自动复制为初始 snapshot(`source='manual_seed_migrated'`),零数据丢失。

### 3. football-data.co 客户端(`app/services/football_data.py`)

| 特性 | 实现 |
|---|---|
| 速率限制 | 滑动窗口 10 req/min(Deque 记录 60s 时间戳) |
| 内存缓存 | 15min TTL(dict 存 `(ts, data)`) |
| 异常分类 | `ApiKeyMissingError`(401)/ `RateLimitedError`(429)/ `FootballDataHttpError`(5xx) |
| 测试友好 | `httpx.MockTransport` 注入 mock |
| 端点支持 | `get_matches_by_date_range` / `get_team` / `get_competition_standings` / `get_competitions` |

**配置(主人需注册免费 token)**:
```env
FOOTBALL_DATA_ENABLED=true
FOOTBALL_DATA_API_KEY=<your_free_token>  # 注册:https://www.football-data.org/
```

### 4. 6h 周期刷新(`app/services/periodic_refresh.py`)

```python
def run_periodic_refresh(db, fb_client=None) -> dict:
    # Step 1: 给所有现有 MatchOdds 追加 snapshot(去重 2s 窗口)
    # Step 2: 可选 fb-data 元数据更新(status / score)
    # Step 3: 写 ApiUsageLog
```

**scope 最小化原则**:
- ✅ fb-data 元数据 + odds 快照打点
- ❌ **不**覆盖 wc26 主同步(15min 实时比分不变)
- ❌ **不**重算 Elo(CPU 密集,数据稳定)

**lifespan startup 立即跑一次**(避免 6h 调度窗口期数据 stale)。

### 5. API 端点

| 端点 | 用途 |
|---|---|
| `GET /api/matches/{id}/odds/history` | 单场赔率时间序列(多公司多时间点) |
| `?bookmaker=bet365` | 过滤单家公司 |

**响应结构**(直接喂给 Chart.js datasets):
```json
{
  "match_id": 1,
  "has_history": true,
  "bookmakers": ["bet365", "pinnacle", "williamhill"],
  "series": {
    "bet365": [{"t": "2026-06-15T12:00", "home_win": 1.85, ...}],
    "pinnacle": [...]
  },
  "count": 9
}
```

### 6. 前端 Chart.js 折线图(`#odds-trend-chart`)

- 集成在 match detail 页(在 renderOddsDetail 之后)
- 三个 tab:主胜 / 平 / 客胜(切换 dataset)
- 6 种颜色区分不同 bookmaker
- 移动端 375px 布局 OK(canvas 自适应)
- 引入 Chart.js 4.4.0 CDN(`jsdelivr.net`)

### 7. 测试

| 类型 | 数量 | 覆盖 |
|---|---|---|
| 单元 | 17 + 6 + 11 = **34 项** | football_data 客户端 + history API + periodic_refresh |
| 集成 | (含在上述) | snapshot 幂等性 / fb-data 错误处理 / scheduler 注册 |
| E2E | **4 项** | canvas 渲染 / 三个 tab / 切换 / 移动端 375px |

**全量回归**:220 passed + 1 skipped(基线 198 → 232 项)+ 15 E2E(基线 11 → 15 项)。

### 8. 已知限制

- **football-data.co 免费层无赔率端点** —— 走势曲线初始平坦(自动打点值不变),未来接付费赔率 API 即可激活真实波动
- **赔率走势需要时间积累** —— 6h 一打点,10 天后才有 40+ 时间点呈现明显波动
- **fb-data token 需主人注册** —— 没 token 时该模块优雅 skip,不影响其他功能

详见 `deliverables/v0.5.1_*_completion_report.md`。

---

## 八、风险与监控

| 风险 | 状态 | 兜底 |
|---|---|---|
| API-Football 100 次/天不够 | 🟢 已接入 | 日预算守护 + worldcup26.ir 备份 + worldcupstats.football 爬虫 + 人工兜底 |
| worldcupstats 抓取失败 | 🟢 已实现降级 | 抓取失败时显示空列表，admin 手动录入 |
| 数据源频繁变化 | 🟢 已监控 | `ApiUsageLog` 记录每次外部调用 + `/api/admin/sync/status` 查看源状态 + v0.14 增加预算告警 |
| 预测偏差大 | 🟢 已声明免责 | UI 显示"仅供参考，不构成投注建议" |

---

## 九、下一阶段（v0.14.x+）

1. **多源评分 v2** — 给每个数据字段（比分、状态、积分榜、事件）赋予置信度权重，自动仲裁冲突值
2. **真实赔率 API 接入**（The Odds API / Betfair 商业 feed）— 让赔率走势 + 模型 vs 市场对比出现真实波动
3. **球员 360° 档案**（手动 + Transfermarkt 自托管）
4. **xG 数据接入**（基于 StatsBomb Open Data event 数据做射门质量建模）
5. **PWA 离线缓存**（赛前 1h 下载比赛包）
6. **预算告警**（API-Football 日调用量 > 80% 时邮件/企业微信通知）

---

## 九点五、v0.7.0a → v0.7.6 模型演进专章（跨版本整合）

> 本节聚焦 v0.7 系列（2026-06-16 一天内密集迭代），沉淀"模型设计 + 实验方法 + 关键发现"，供后续 v0.7.7+ 与 v0.8.x 借鉴。

### 演进路线图

```
v0.6.0 (Glicko-2 独立)
  ↓ 发现 G2 单独 62.65% > Elo 56.63% (+6.02pp)
v0.7.0a (ModelBlend 50/50 加权平均)
  ↓ 端点 + 单元测试
v0.7.0b (lifespan auto_log + 3-tab UI)
  ↓ 用户开始用 blend
v0.7.1 (Monte Carlo 10000 sims)
v0.7.1.1 (MC 缓存层 6h)
  ↓ 用户开始看夺冠概率
v0.7.2 (odds_api_client + model_vs_odds compare)
v0.7.2.1 (前端赔率接入)
v0.7.2.3 (赔率 vs 模型概率走势)
v0.7.4 (Weight Sweep 7 组)
  ↓ 关键发现: G2 单独 brier 最低
v0.7.5 (Adaptive Weight 4 段按距上次比赛天数)
  ↓ 保留 v0.7.0a 50/50 默认, Adaptive 为可选升级
v0.7.6 (StatsBomb 2018 补 4 场 → 1226 场训练集)
  ↓ 不重训, 只为 v0.7.7+ 准备好数据
```

### 关键发现（必须 push back 过的结论）

| 版本 | 发现 | 决策 |
|---|---|---|
| v0.7.4 weight sweep | Glicko-2 单独 (w_g2=1.0) brier **0.5120** / accuracy **0.6265** 显著优于 v0.7.0a 50/50（brier 0.5296 / acc 0.6123） | **主人方案 B：不回滚默认**，保留 50/50 作为保守基线，新增 v0.7.5 Adaptive Weight 作为可选升级 |
| v0.6.0 top-bias | 主队轻微高估 + 平局低估 | v0.7.8 计划做 Platt scaling 校准 |
| v0.7.6 数据集 | Hicruben 0 场 2018+2022 大赛，StatsBomb 100% 覆盖 6 大赛 | **不重训**：64 场大赛会拉低 913 场友谊赛权重；只准备好数据 |

### 训练集演进

| 版本 | Hicruben | StatsBomb | 合计 | 球队覆盖 |
|---|---|---|---|---|
| v0.1.2 → v0.6.0 | 913 | 309 | 1222 | 187+76=263（含 Hicruben/StatsBomb 并集） |
| v0.7.6 后 | 913 | **313**（+4 场 2018 WC 补齐） | **1226** | 191 队并集，72 队交集 |

**注意**：191 队含历史 + 未来 2026 队，远超 48 强；**实际训练用 187 场 Hicruben + 76 场 StatsBomb 历史比赛**，含归一化处理。

### Adaptive Weight 设计理由（v0.7.5）

```python
SEGMENT_WEIGHTS = {
    FRESH (≤7d):   w_elo=0.0, w_g2=1.0  # 新鲜数据，信任 G2
    WARM  (7-30d): w_elo=0.2, w_g2=0.8  # G2 稍 stale
    STALE (30-90d):w_elo=0.4, w_g2=0.6  # 数据陈旧
    DORMANT (>90d):w_elo=0.5, w_g2=0.5  # 退回 v0.7.0a baseline
}
```

**为什么保守设计**：
- 主人明确选方案 B（不回滚默认）→ Adaptive 是可选升级，不是默认替换
- DORMANT 段回 50/50 是 fail-safe，避免极端权重组合在缺数据时拉低精度
- `days_since_last_match()` 取 `max(home_days, away_days)` 是保守估计，避免低估数据陈旧风险
- 没数据时返回 9999 (DORMANT)，不返回 0（避免被误判为 FRESH）

### 架构原则（跨 v0.7 共用）

1. **Walk-forward 训练 + 测试** — 不打乱时间顺序，按比赛时间 split；这是赛果预测的硬约束
2. **4 指标评估** — accuracy / brier / log_loss / roi_uniform，winner 选 brier 最低（最严格）
3. **prediction_log 表是所有模型横评基础** — v0.6.0 引入，v0.7.0b lifespan 自动写，v0.7.4 sweep 用，v0.7.8 校准用
4. **缓存层不影响功能** — MCRunHistory 只加 `cached` / `cache_age_seconds` 可选字段，不破坏前端
5. **`?refresh=1` 必须透传到缓存层** — 用户/调度都有强制刷新权

### v0.7.6 数据回填动机与边界

**动机**：v0.7.4 sweep 显示 G2 在 913 场友谊赛训练上 62.65%，但 Hicruben 完全缺失 2018+2022 世界杯正赛。StatsBomb 补 4 场让训练集首次覆盖这两届大赛。

**边界（诚实 push back）**：
- ❌ **不重跑 1226 场 walk-forward**（v0.7.4 结论基于 913 场，重训后 64 场大赛会拉低精度）
- ❌ **不回写 Hicruben 主模型**（同理由）
- ❌ **不重写 prediction_log**（v0.6.0 913 行 backfill 是干净的）
- ✅ **只准备好数据**（`data/v0.7.6_data_coverage_report.md`），等 v0.7.8 calibration 时再消费

### 未来改进路径

- v0.7.7 → README 整合（本版本）
- v0.7.8 → prediction calibration + 1226 场 walk-forward
- v0.8.0 → 真 MarketBlend（Elo + G2 + 市场隐含概率三方加权）
- v1.0.0 → 世界杯开赛（2026-06-11 之后实时精度报告 + 跨模型校准正式启用）

---

## 九点六、v0.7.8 → v0.7.10 校准实验专章（Platt + Isotonic + Cockpit 速览） ⚠️ **v0.8.1 已关停**

> **v0.8.1 关停**: G2 后验校准（Platt + Isotonic）未达 1.5pp brier 改进门槛，已下线。
> 端点 `/elo/calibrated-predict/*` 和 `/elo/calibration-summary` 返回 **410 Gone**。
> UI 第 5 个 tab "Calibrated" 移除, Cockpit mini-card 移除。
> prediction_log v7c/v7d 行通过 Alembic migration `f3a9b2c1d4e6` 清理。
> **git 历史保留 v0.7.8/9/10 commit, 可 `git checkout v0.7.8` 恢复运行时端点**。
> 详细关停报告见 `deliverables/v0.8.1_calibration_sunset.md`。

> 本节聚焦 v0.7.8/9/10 三天迭代的"模型校准"实验结论（**已存档**）。所有结果基于 913 场 Hicruben walk-forward 验证（v0.7.6 补的 4 场未注入实验，避免精度波动）。

### 1. 校准动机

v0.6.0 `get_top_prediction_bias()` 已暴露"主队轻微高估 + 平局低估"的系统性偏差。理论上 Platt scaling（逻辑回归参数化重映射）和 Isotonic regression（非参数单调保序）都能修正这种偏差。

### 2. 双方法实测结果（913 场）

| 方法 | Full fit brier | Walkforward 80/20 brier | Walkforward 80/20 accuracy | 1.5pp 门槛 |
|---|---|---|---|---|
| **G2 raw (baseline)** | 0.5120 | 0.4793 | 66.67% | - |
| G2 + Platt | **0.5052 (-0.69 pp)** | 0.4766 (-0.27 pp) | 65.57% | ❌ |
| G2 + Isotonic | **0.5044 (-0.77 pp)** | 0.4770 (-0.23 pp) | **66.12%** | ❌ |

**核心结论**：
- ✅ **brier 总 < raw**（概率分布更接近真实，不是 placebo）
- ⚠️ **收益边际**（Full fit -0.69/-0.77pp，Walkforward 仅 -0.23/-0.27pp）
- ⚠️ **argmax 几乎不变**（accuracy 持平甚至 walkforward 倒退 1.10pp）
- ❌ **未达 1.5pp 门槛**

### 3. PAVA 步阶 Isotonic 的陷阱

```python
# Isotonic 比 Platt 更易过拟合：
# Full fit -0.77pp（看起来更优） → Walkforward -0.23pp（实际泛化能力变差）
# PAVA 步阶在 913 场全样本上能拟合出更复杂的非参数映射，但留出 20% 测试集时表现明显下降
```

**推荐用法**：高/关键场预测时用 Calibrated（概率分布更准），普通场用 v3_g2（argmax 选择更稳）。

### 4. 端点与缓存设计

| 端点 | 方法 | 说明 |
|---|---|---|
| `GET /api/elo/calibrated-predict/{home}/{away}` | `?model=glicko2|elo|blend&method=platt|isotonic|both` | 单场预测 + `experimental=true` 标识 |
| `GET /api/elo/calibration-summary` | - | 摘要级数据（Cockpit mini-card 用） |

**性能保障**：
- 单场端点实时 walkforward（~100ms/次，符合 README §七·B "Elo 单场 < 200ms" 基线）
- 摘要端点 **进程内 6h cache + double-checked locking**，Cockpit 60s 刷新不重算 913 场（cache hit < 10ms）

### 5. Cockpit 4-th Calibrated Tab + mini-card（v0.7.9 + v0.7.10）

```
┌──────────────────────────────────────────────────────────┐
│ G2 校准 brier 速览                                        │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│ │ Platt Full   │  │ Platt 80/20  │  │ Isotonic 80/20│   │
│ │   +0.69 pp   │  │   +0.27 pp   │  │   +0.23 pp   │    │
│ │  🟢 训练样本  │  │  🟢 真实泛化 │  │  🟢 PAVA 步阶 │    │
│ │    913 场    │  │              │  │              │    │
│ └──────────────┘  └──────────────┘  └──────────────┘    │
│ 训练样本 913 场 · 缓存 6h · computed_at 2026-06-17T...   │
└──────────────────────────────────────────────────────────┘
```

3 列彩色卡片直接渲染在 `/#/cockpit` 路由，**用户无需切到 `/#/elo` Calibrated tab 就能秒懂校准状态**。

### 6. 诚实 push back 过的边界

| 决策 | 理由 |
|---|---|
| ❌ **不替换 v3_g2 默认** | Calibration 收益边际，不达 1.5pp 门槛；改默认会引入 regression 风险 |
| ✅ **作为 experimental 端点保留** | 用户可手动选择使用；高/关键场推荐 Calibrated |
| ✅ **Cockpit mini-card 透明展示** | 不藏数据，让用户自行判断 |
| ❌ **不做 1226 场 walkforward** | v0.7.6 已诚实 push back，64 场大赛会拉低精度 |
| ❌ **prediction_log 不加 5-th model**（v0.8.1 候选） | 校准收益边际，长期数据收集 ROI 不明 |

### 7. v0.8.x 校准演进路径

- v0.8.1 候选 → prediction_log 加 calibrated（Platt + Isotonic）双写，6-12 月后回测
- v0.8.2 候选 → 1226 场联合 walkforward，验证边际收益是否在大赛数据下放大
- v1.0.0 → 世界杯开赛实时精度报告 + 校准正式启用（达到 1.5pp 才切换默认）

---

## 十、变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-12 | v0.1.0 | 首周 MVP：抓取 + API + 预测 + 手动兜底 + 42 项测试全过 |
| 2026-06-13 | v0.1.1 | T1 接入 Alembic 迁移（init + F2 + M1 配套表），95/95 测试全过 |
| 2026-06-13 | v0.1.2 | M1 Elo 评级：Hicruben 913 场真实数据 + Dixon-Coles，4 年 walk-forward RPS 0.20 / 准确率 58.3%，5 个新 API 端点 |
| 2026-06-13 | v0.1.3 | M1.5 前端 Elo 卡片：`/#/elo` 新页面（48 队全榜 + 1v1 对比器 + 回测指标），抽屉入口，4 张 Playwright 截图，95/95 测试无破坏 |
| 2026-06-13 | v0.1.4 | M2 增强 Elo：Elo + form + H2H 加权因子，新端点 `/api/elo/predict-enhanced`，v1 vs v2 双返回；form 4 队生效 / H2H 14 对决数据基础有限 |
| 2026-06-13 | v0.1.5 | P1.2 Elo CSV 导出：Elo 页 header 加"导出 CSV"按钮，63 队 Elo 全榜 + 10 字段 + UTF-8 BOM（Excel 中文友好），RFC 4180 转义，3 张截图 + 实测导出文件，95/95 测试无破坏 |
| 2026-06-13 | v0.1.6 | P1.3 历史交锋详情页：新路由 `/#/h2h/{code1}/{code2}`，后端新端点 `GET /api/h2h/{code1}/{code2}` + `GET /api/teams/{code}/h2h-opponents`，match detail H2H 卡片"📜 完整历史 →"入口，视角归一（code1/code2 互换时胜负自动翻转），5 张截图 + 6/6 Playwright 测试，95/95 测试无破坏 |
| 2026-06-13 | v0.1.7 | **数据同步链路修复**：(1) `full_sync()` 接受 db 参数（修复 scheduler 5 次连续 fail 的 `takes 0 positional arguments` bug）；(2) `sync_matches` 改用 `wc26_id → fifa_code` 映射（修复 4/6 场主客队错位）+ `wc26_id → stadium_name` 映射（修复 4/5 球场错位）；(3) `app.main.lifespan` 启动时立即跑一次 `worldcup26_full_sync(db)` 避免 15min 调度窗口期内数据 stale。**修复影响**：6/12 CAN 1-1 BIH / USA 4-1 PAR；6/13 QAT vs SUI / BRA vs MAR / HAI vs SCO / AUS vs TUR 全部主客队 + 球场显示正确，95/95 测试无破坏 |
| 2026-06-14 | v0.1.8 | **P1.2 CSV 导出收尾 + P1.3 H2H 主页**：(1) `exportEloToCSV()` 加 `_has_team` 过滤，只导 48 队（按钮 title "48 队" 与实际一致）；(2) 新增 `renderH2H()` 主页（选队 select + 对手卡片网格，PC 3 列 / 移动单列）；(3) 抽屉菜单加 "⚔️ 历史交锋" 入口；(4) 路由表 + skeletonTypeForHash + showSkeleton 注册 `'/h2h'`；(5) **修 h2h 路由 9 队非参赛队 fallback**（CMR/CRC/DEN/ISL/PER/POL/RUS/SRB/WAL，未晋级 2026 但有 2018+2022 种子），用 type() duck typing 构造 fallback dict。**Playwright 端到端验证**：49 行 CSV（含 UTF-8 BOM）+ 默认 BRA 9 对手 + 切换 MEX 7 对手 + 详情页跳转 BRA vs SRB（2 场 + 🏳️ SRB fallback 显示）+ 移动端 375px；4 张截图 `docs/screenshots/P1.2_P1.3/01-05_*.png`；95/95 测试无破坏 |
| 2026-06-15 | **v0.2.0** | **全面 audit + 数据完整性 + 时区现代化**：(1) **P0-1 standings 错位修复** — `sync_standings` 复用 `wc26_id → fifa_code` 映射（与 sync_matches 一致），清 18 条错位（id 49-66），重启 lifespan 同步后 12 组 × 4 队 = 48 条全对齐，7 个关键错位队（USA/QAT/ESP/FRA/ENG/GER/BRA）standing.group_name = team.group_name；(2) **P0-3 datetime.utcnow 21 处替换** — 7 个文件 + models.py 6 处 Column default（`default=lambda: datetime.now(timezone.utc)`），跑测试时 136 个 DeprecationWarning 全消；附带修 `prediction_cache.py` 的 naive/aware datetime 比较 bug（DB 存的 DateTime 是 naive，比较时 `replace(tzinfo=utc)`）；(3) **P1-1 API team_id 改 path** — `team_id: int` 改 `team_code: str`，自动兼容 int ID（`/api/teams/11`）和 FIFA 3 字母代码（`/api/teams/BRA` 或 `mex`），加 `_resolve_team()` helper；(4) **README v0.2.0 重写** — §1.1 扩 API 列表到 31 端点，§1.2 删已实现 Non-Goals（出线模拟/WebSocket），§2 目录树扩到 9 routers + 9 services，§2.1 数据流图加 worldcup26.ir 链路，§6 API 速查分 4 子表（核心数据 10 + Elo+H2H+模拟器 9 + 管理 11）含 weather 等补端点，§10 加 v0.2.0 一条；**95/95 测试零回归**；**P1-1 端到端验证**：`/api/teams/11` → 巴西（ID 兼容），`/api/teams/BRA` → 巴西（fifa_code），`/api/teams/mex` → 墨西哥（大小写不敏感），`/api/teams/BRA/matches` → 3 场，`/api/teams/XXX` → 404 |
| 2026-06-15 | **v0.2.1** | **部署修复**：(1) 重启生产服务器加载 v0.2.1 代码；(2) 修复 `/health` version 硬编码问题（改为 `app.version`）；(3) SQL 修复 92 场 `status=live` 但 `time_elapsed=notstarted` 的比赛为 `scheduled`；(4) **118 项 pytest + 6 项 Playwright E2E 全绿** |
| 2026-06-15 | **v0.3.0** | **Bracket 真实数据接入**：(1) 新增 `app/services/bracket_logic.py` — 12 组排名、8 个最佳小组第三、2026 Annex C R32 对阵生成、Elo 预测；(2) 新增 `GET /api/bracket` 返回完整对阵树（R32/R16/QF/SF/3rd/Final）；(3) 新增 `POST /api/admin/bracket/rebuild` 手动触发重算；(4) 前端 `/#/bracket` 接入 `/api/bracket` 真实数据，渲染 Elo 胜率条；(5) 新增 `tests/test_bracket.py` 12 项单元/集成测试；(6) 新增 Playwright E2E `test_bracket_page_renders`；(7) **README v0.3.0 更新**：API 端点 33 个，测试 130+7 项；**130 项 pytest + 7 项 Playwright E2E 全绿** |
| 2026-06-15 | **v0.3.1** | **Bracket 自动重算**：(1) 新增 `bracket_logic.should_auto_rebuild()` — 无状态判断小组赛是否全部结束且 R32 尚未落位；(2) 扩展 `app/services/scheduler.py`，注册每 15 分钟一次的 `_job_bracket_auto_rebuild` 任务，满足条件时自动调用 `rebuild_bracket()`；(3) 防重复触发：R32 全部填入真实球队后不再执行；(4) 扩展 `tests/test_bracket.py`：5 项新测试覆盖 `should_auto_rebuild` 三种状态 + scheduler job 触发/跳过；(5) 版本号 bump 至 0.3.1；**136 项 pytest + 7 项 Playwright E2E 全绿** |
| 2026-06-15 | **v0.4.0** | **StatsBomb Elo 双数据源**（对比源，Hicruben 保持默认）：(1) 新增 `app/services/statsbomb_elo.py` + `scripts/download_statsbomb.py` + `scripts/build_statsbomb_from_extracted.py`，基于 StatsBomb Open Data 309 场国际大赛训练中性场地 Elo；(2) `app/services/elo.py` 全接口支持 `source=hicruben|statsbomb`，缺失球队自动 fallback 到 Hicruben；(3) `app/routers/elo.py` 所有 Elo 端点加 source 参数，新增 `GET /api/elo/compare/{home}/{away}` 并排对比；(4) 前端 Elo 页加数据源切换按钮、StatsBomb 说明与 fallback 提示；(5) 新增 `data/seed/statsbomb/statsbomb_elo.json` + `attribution.md` 满足许可证要求；(6) 新增 `tests/test_statsbomb_elo.py` 16 项测试；(7) 版本号 bump 至 0.4.0；**152 项 pytest + 7 项 Playwright E2E 全绿** |
| 2026-06-15 | **v0.5.0** | **市场赔率模块 M3**（手动录入 + value bet 算法）：(1) 新增 `match_odds` 表 + Alembic 迁移 `b1c5e7f9a2d3`；(2) 新增 `app/services/odds_service.py` — `decimal_to_implied_prob` / `remove_vig` / `value_bet` / `compute_market_probabilities` / `compare_odds_vs_elo` / `aggregate_multi_bookmaker`；(3) 新增 `app/routers/admin_odds.py` — `POST /api/admin/odds`（单条覆盖式）+ `POST /api/admin/odds/batch`（批量 + 失败明细）+ `DELETE /api/admin/odds/{id}`，均需 `X-Admin-Token`；(4) 新增 `app/routers/odds.py` — `GET /api/matches/{id}/odds`（consensus + 去 vig 市场概率）+ `GET /api/odds/compare`（未完赛 vs Elo）+ `GET /api/odds/value-bets?min_rate=0.05`（TOP N 价值投注）；(5) 前端 3 处接入 — matchCard 底部赔率角标、match detail 完整赔率卡（含 vig 透明度）、新页面 `/#/odds`（价值投注高亮 amber）；(6) 新增 `tests/test_odds_service.py` (18) + `tests/test_admin_odds.py` (13) + `tests/test_odds_api.py` (10) + `tests/e2e/test_odds.py` (4)；(7) 版本号 bump 至 0.5.0；(8) README §七·H 新增 M3 详细文档；(9) ⚠️ 重要声明：本模块**仅供分析参考，不构成投注建议**，v0.5.1+ 可接入 football-data.co API；**193 项 pytest + 11 项 Playwright E2E 全绿** |
| 2026-06-15 | **v0.5.1** | **赔率走势 + 多源数据接入 + 6h 周期刷新**：(1) 新增 `app/services/football_data.py` — httpx 客户端 + 滑动窗口限速(10 req/min) + 内存缓存(15min TTL) + 异常分类 + `httpx.MockTransport` 注入测试；(2) 新增 `OddsSnapshot` 表 + Alembic 迁移 `b9c4d8e2f1a3`（自动从 v0.5.0 `match_odds` 迁移 9 条种子）+ 复合索引 `(match_id, bookmaker, snapshot_at)`；(3) 新增 `GET /api/matches/{id}/odds/history` 端点（按 bookmaker 分组 + 时间升序 + 支持过滤）；(4) 新增 `app/services/periodic_refresh.py` — `take_odds_snapshots`（2s 窗口去重幂等）+ `refresh_match_metadata_from_football_data`（仅当 enabled + 有 key 时执行，失败写 ApiUsageLog）+ `run_periodic_refresh` 编排；(5) 扩展 `app/services/scheduler.py` — 新增 `_job_periodic_refresh` 6h 调度 + lifespan startup 立即跑一次避免 stale；(6) 前端 `app/static/index.html` + `js/app.js` — Chart.js 4.4.0 CDN + 走势图 canvas + 三个 tab(主胜/平/客胜) + 移动端 375px 适配；(7) 新增 `tests/test_football_data.py` (17) + `tests/test_odds_history_api.py` (6) + `tests/test_periodic_refresh.py` (11) + `tests/e2e/test_odds_trend.py` (4)；(8) 版本号 bump 至 0.5.1；(9) ⚠️ **football-data.co 实际需要免费 token**（5 分钟注册，主人需在 .env 填 `FOOTBALL_DATA_API_KEY=<token>`）；**220 项 pytest + 15 项 Playwright E2E 全绿**；详见 `deliverables/v0.5.1_completion_report.md` |
| 2026-06-16 | **v0.6.0** | **准确率 dashboard + 历史回填 + 3 模型横评**：(1) 新增 `app/services/glicko2.py` (351 行) — Python 原生 Glicko-2 实现（无第三方依赖，含 RD 衰减 + 12 期窗口 + 双排名期 vol/rating 同步更新）；(2) 新增 `PredictionLog` 表 + Alembic 迁移 `c4f7b9e1a2d3`（记录"赛前预测概率 + 实际结果"回测用）；(3) 新增 `app/services/prediction_log.py` (297 行) — `record_prediction` / `settle_pending_predictions` / `compute_accuracy_stats`（综合准确率 + 1X2 胜率分布 + RPS/Brier/LogLoss）+ `get_top_prediction_bias`（Top N 偏差复盘，主队高估 / 客队高估 / 平局高估）+ Brier/LogLoss 辅助函数；(4) 新增 4 端点：`GET /api/elo/glicko2-ratings` + `GET /api/elo/glicko2-metrics`（Glicko-2 独立指标：RD/σ/volatility 分布）+ `GET /api/elo/accuracy-stats`（含 Glicko-2 横评）+ `GET /api/elo/top-bias?limit=10`（可按偏差方向过滤）；(5) 前端 3 处接入 — `/#/cockpit` mini-card 3 模型横评 + `/#/accuracy` 完整 3 模型对比表（含 RPS/Brier/LogLoss/Top 偏差）+ `/#/odds` "数据更新于 X 分钟前"（呼吸圆点 + 颜色分级）；(6) 新增 `scripts/backfill_prediction_log.py` (285 行) — walk-forward 913 场 Hicruben 数据，1x2 + 实际结果写入 prediction_log，产物 `data/prediction_log_backfill.jsonl`（1826 行 = 913 Elo + 913 Glicko-2）+ `data/backfill_report.md`；(7) 新增 `tests/test_glicko2.py` (17) + `tests/test_prediction_log.py` (15)；(8) 版本号 bump 至 0.6.0；(9) **Glicko-2 实测 62.65% vs Elo 56.63%（+6.02 pp），Top 10 偏差显示"主队轻微高估 + 平局低估"** —— 后续 v0.7+ 可考虑 market blend 校准；**276 项 pytest + 1 skipped + 15 项 Playwright E2E 全绿**；详见 `deliverables/v0.6.0_completion_report.md` + `data/backfill_report.md` |
| 2026-06-16 | **v0.7.0a** | **ModelBlend (Elo + G2 加权平均) + 端点**：(1) `app/services/blend.py` `predict_match_blend(home, away, w_elo, w_g2, ...)` — `w_elo + w_g2 = 1.0` 校验，winner 选 max prob；(2) `app/routers/elo.py` 新增 `GET /api/elo/predict-blend/{home}/{away}?w_elo=0.5&w_g2=0.5&match_id=` — match_id 自动写 prediction_log model=v7a_blend；(3) 修 Glicko-2 USA/MEX 大写 fallback；(4) 11 测试（8 函数层 + 3 端点层 200/404/422）；(5) commit `844190a` + **git tag v0.7.0a**；**E2E 5 场景全 PASS（BRA/ARG 等权 0.3948 = 0.5×0.3940 + 0.5×0.3956 数学完全一致，w_elo=0.7 → 0.3945）** |
| 2026-06-16 | **v0.7.0b** | **Lifespan 自动写 prediction_log + 前端 3-tab UI**：(1) `auto_log_predictions()` 服务 + 3 模型注册表（elo / glicko2 / blend）；(2) `app/main.py` lifespan startup 立即跑一次 + 6h scheduler 周期刷新 step 3；(3) `app/static/js/app.js` `/#/elo` 3-tab (Elo / Glicko-2 / Blend) + Glicko-2 评分榜折叠；(4) 8 集成测试 + 7 e2e + 3 UI tab 断言；(5) commit `e9c6635` + **git tag v0.7.0b**；**280 passed + 1 skipped, 184.62s, 零回归** |
| 2026-06-16 | **v0.7.1** | **Monte Carlo Tournament 整届 10000 次模拟**：(1) `app/services/monte_carlo.py` `simulate_full_tournament()` — 48×48 prob_matrix 预计算 + 二叉树淘汰赛推进；(2) `GET /api/simulator/tournament` 端点 + Simulator 页 MC section；(3) `tests/test_monte_carlo.py` 11 unit/集成 + `tests/e2e/test_mc_e2e.py` 6 e2e + `deliverables/v0.7.1_spec.md` / `v0.7.1_release.md`；(4) commit `b17ddaf` + **git tag v0.7.1**；**10000 sims ≈ 4s**（预算 15s）；**291 passed + 1 skipped**（非 E2E）；实测 FRA 13.1% / ESP 13.0% / GER 10.4% |
| 2026-06-16 | **v0.7.1.1** | **Monte Carlo 缓存层**：(1) `MCRunHistory` 表（Alembic `e916a40edd77`） + `load/save/run_mc_with_cache()`；(2) `/api/simulator/tournament?refresh=` 强制刷新；(3) 6h scheduler warmup；(4) `tests/test_mc_cache.py` 7 测试 + `tests/e2e/test_mc_cache_e2e.py` 2 测试 + `tests/e2e/conftest.py` 覆盖使用生产 DB；(5) commit `b137458` + **git tag v0.7.1.1**；**298 passed + 1 skipped + 31 E2E**；默认参数第二次请求 **~4s → <50ms** |
| 2026-06-16 | **v0.7.2** | **odds_api_client + 模型对比**：(1) `app/services/odds_api_client.py` — football-data.co 客户端（滑动窗口限速 10 req/min + 15min 缓存 + Mock 注入）；(2) `compare_model_vs_odds()` 服务（支持 elo/glicko2/blend）+ `compute_value_bets()` 按模型筛选；(3) 3 新端点 `/odds/compare-model` / `/odds/value-bets-model` / `/odds/service-status`；(4) 10 测试；(5) commit `acaa0ee` + **git tag v0.7.2**；**310 passed + 1 skipped + 40 E2E** |
| 2026-06-16 | **v0.7.2.1** | **前端赔率接入 v0.7.2 新端点**：(1) 顶部"服务状态"小卡；(2) 赔率卡模型下拉（Elo / Glicko-2 / Blend，默认 Blend）；(3) "按模型筛选价值投注" 新 section（模型 + 最低价值双控件）；(4) v0.5.1 旧 API 路径保留；(5) commit `0122737` + **git tag v0.7.2.1**；**310 passed + 1 skipped + 43 E2E** |
| 2026-06-16 | **v0.7.2.3** | **赔率 vs 模型概率走势对比**：(1) `/api/odds/{id}/history?model=` 支持模型参数；(2) 走势图叠加模型预测概率（半透明线）；(3) Chart.js 4.4.0 升级；(4) `tests/test_odds_history_model.py` 8 测试；(5) commit `0a3da9b` + **git tag v0.7.2.3**；**310 passed + 1 skipped + 46 E2E** |
| 2026-06-16 | **v0.7.4** | **Weight Sweep**：(1) `app/services/weight_sweep.py` — 7 组权重 (1.0,0.0)~(0.0,1.0) + 4 指标 (accuracy / brier / log_loss / roi_uniform)，winner 选 brier 最低；(2) `/api/elo/weight-sweep` 端点；(3) Cockpit mini-card 渲染；(4) `tests/test_weight_sweep.py` 8 unit + `tests/e2e/test_weight_sweep_e2e.py` 3 e2e；(5) commit `bd42a24` + **git tag v0.7.4**；**326 passed + 1 skipped + 53 E2E**；**关键发现**：Glicko-2 单独 (w_g2=1.0) brier 最低 0.5120 / accuracy 0.6265，v0.7.0a 50/50 默认是次优解（brier 0.5296 / acc 0.6123）—— 主人选方案 B（保留默认 + 加 Adaptive） |
| 2026-06-16 | **v0.7.5** | **G2 Adaptive Weight**（按距上次比赛天数分段）：(1) `app/services/adaptive_weight.py` 4 段 (FRESH ≤7d / WARM 7-30d / STALE 30-90d / DORMANT >90d) + `days_since_last_match()` + `adaptive_weight_blend()` + `walkforward_adaptive_validate()`；(2) `/api/elo/adaptive-weight/{home}/{away}` 端点（match_id 自动写 prediction_log model=v7b_adaptive）；(3) `/elo` 4-tab UI（Elo / Glicko-2 / Blend / **Adaptive**）；(4) 11 unit + 3 e2e 测试；(5) commit `36bae24` + **git tag v0.7.5**；**337 passed + 1 skipped + 56 E2E**；v0.7.0a 50/50 默认保留，Adaptive 为可选升级 |
| 2026-06-16 | **v0.7.6** | **数据回填 2018+2022 扩训练集**：(1) StatsBomb 2018 WC 补 4 场 (Colombia 1-2 Japan / Japan 2-2 Senegal / Denmark 0-0 France / **South Korea 2-0 Germany**) → 60→64 场；(2) 重新生成 `statsbomb_elo.json` 309→313 场（matchesApplied +4）；(3) 数据覆盖报告 `data/v0.7.6_data_coverage_report.md`：合并 1226 场 / 时间 2018-06-14→2026-06-11 / 191 队 / StatsBomb 6 大赛 100% 覆盖 / Hicruben 0 场 2018+2022；(4) 4/4 v0.7.6 专项测试 PASS；(5) commit `7c40dd7` + **git tag v0.7.6**；**393 passed + 1 skipped + 56 E2E**（零回归）；**诚实 push back 边界**：不重训 1226 场 walk-forward / 不回写 Hicruben 主模型 / 不重写 prediction_log（v0.7.4 结论基于 913 场友谊赛，64 场大赛会拉低精度） |
| 2026-06-17 | **v0.7.7** | **README 整合 v0.7.0a–v0.7.6 跨版本专章**（用户文档 2h）：(1) 头部版本/阶段/作用域刷新至 v0.7.7；(2) §1.1 范围表扩 API 端点 40→49 + 新增 G2/ModelBlend/Adaptive/MC/Sweep/回填 6 行；(3) 新增 **§九点五 v0.7 模型演进专章**（演进路线图 + 关键发现 + 训练集演进 + Adaptive 设计理由 + 架构原则 + v0.7.6 动机与边界 + 未来路径）；(4) §9 下一阶段改写为 v0.7.8+ 校准/真实赔率 API；(5) §10 变更日志追加 v0.7.0a/b、1、1.1、2、2.1、2.3、4、5、6 共 10 条（每条含 commit + tag + 测试 + 关键发现） |
| 2026-06-17 | **v0.7.8** | **G2-only Platt scaling (experimental)**：(1) `app/services/calibration.py` 5 函数（`platt_fit`/`platt_apply` 梯度下降 2000 步 lr=0.05 + `fit_calibrators` + `calibrate_probs` + `walkforward_validate`）；(2) `app/routers/elo.py` `GET /api/elo/calibrated-predict/{home}/{away}?model=glicko2\|elo\|blend` 端点（match_id 自动写 prediction_log model=v7c_calibrated_platt，返回 `experimental=true` 标识）；(3) 13 unit + 3 e2e PASS；(4) 913 场 Hicruben 训练（v0.7.6 补的 4 场未注入），brier 0.5120 → 0.5052（**-0.69 pp**），walkforward 80/20 0.4793 → 0.4766（**-0.27 pp**），**未达 1.5 pp 门槛**；(5) commit `b7fcd0a` + **git tag v0.7.8**；**354 passed + 1 skipped + 59 E2E**（零回归）；**主人决策 A 方案"标 experimental 推进"**——高/关键场用 calibrated，普通场用 v3_g2 |
| 2026-06-17 | **v0.7.9** | **G2 校准实验 + Cockpit 4-th Calibrated Tab**：(1) `app/services/isotonic_calibration.py` 204 行（PAVA 步阶 + walkforward 校验 + scipy-free 实现）；(2) `calibrated_predict` 端点加 `?method=platt\|isotonic\|both` Query 参数 + 新增 `calibration_metrics` 字段（实测 platt_full/wf + iso_wf 共 3 个 pp 值，**替代硬编码 0.69/0.23**）；(3) **修诚实硬编码**：router 端 `brier_improvement_pp: 0.69/0.23` 改为实时 walkforward + evaluate_all 重算；(4) **Cockpit 第 5 个 tab "Calibrated"**：Platt + Isotonic 双方法对比 + 推荐 badge + 3 个 brier metric 卡片；(5) `tests/e2e/test_isotonic_calibration_e2e.py` 4 e2e + `tests/e2e/test_v079_calibrated_tab_e2e.py` 3 e2e；(6) 2 张截图（desktop 1440×900 + mobile 375×812）；(7) commit `61ab98d` + **git tag v0.7.9**；**364 passed + 1 skipped + 66 E2E**（零回归）；**Isotonic 反而比 Platt 过拟合更严重**（full -0.77pp vs walkforward -0.23pp，PAVA 步阶在 913 场全样本上拟合复杂映射但泛化能力下降）|
| 2026-06-17 | **v0.7.10** | **Cockpit mini-card 加 G2 校准 brier 速览**（1h）：(1) `app/services/calibration.py` 新增 `get_calibration_summary()` 函数（含 6h 进程内 cache + double-checked locking）；(2) `app/routers/elo.py` 新增 `GET /api/elo/calibration-summary` 端点（轻量摘要级数据，无 home/away 概念，cache hit < 10ms）；(3) 前端 `/#/cockpit` 新增 mini-card（3 列彩色卡片：Platt Full +0.69pp / Platt 80/20 +0.27pp / Isotonic 80/20 +0.23pp，**用户无需切到 `/#/elo` Calibrated tab 就能秒懂校准状态**）；(4) 数字 +/- 符号 + 绿/红颜色按 `pp ≥ 0` 判定（防止 walkforward 倒退时误导）；(5) 2 unit + 2 e2e PASS；(6) 2 张截图（desktop + mobile-375）；(7) commit `5dcb026` + **git tag v0.7.10**；**353 passed + 1 skipped + 66 E2E**（+1 端点 +1 mini-card） |
| 2026-06-17 | **v0.8.0** | **README 整合 v0.7.7–v0.7.10 跨版本专章**（用户文档 2h）：(1) 头部版本/阶段/作用域刷新至 v0.8.0（v0.7.x 模型演进 + 赔率深化 + 缓存 + Adaptive + 数据回填 + G2 校准实验 + Cockpit 速览）；(2) §1.1 范围表扩 API 端点 49→**59** + 新增 "G2 校准实验" 1 行 + 测试数 393+56 → **365+66**（含 calibration 5 unit + 7 e2e）；(3) 新增 **§九点六 v0.7.8-v0.7.10 校准实验专章**（动机 + 双方法实测表 + PAVA 步阶陷阱 + 端点与缓存 + Cockpit mini-card 示意图 + 诚实 push back 边界 + v0.8.x 演进路径）；(4) §9 下一阶段改写为 v0.8.x+（prediction_log 5-th model / 真实赔率 API / 校准 v2 / 球员档案 / xG / PWA）；(5) §10 变更日志追加 v0.7.8/9/10 共 3 条（每条含 commit + tag + 测试 + 实测数据 + push back 边界） |
| 2026-06-17 | **v0.14.0** | **多源数据接入：API-Football + football-data.org + 多源回退**：(1) `app/config.py` 新增 API-Football / football-data.org 配置 + `ApiUsageLog` 表；(2) `app/services/api_football.py` 客户端（滑动窗口限速 10 req/min + 日预算守护 + 内存缓存 + mock 注入）；(3) `app/services/api_football_sync.py` 赛程/积分榜/事件同步；(4) `app/services/multi_source_sync.py` 编排器 — API-Football 优先，失败回退 worldcup26.ir，football-data.org 低频增强，字段级投票仲裁；(5) `app/services/scheduler.py` 注册 6h 全量 + 15min 实时 + 1h 积分榜任务；(6) `app/routers/admin_sync.py` 新增 `/sync/full`、`/sync/live` + `/sync/status` 扩充电源状态；(7) `app/routers/health.py` 增加数据源状态；(8) 新增 `tests/test_api_football*.py` 11 单元 + `tests/test_multi_source_sync.py` 8 集成 + `tests/e2e/test_admin_sync_e2e.py` 2 E2E；(9) 更新 `.env.example` 与 README 数据流/API 速查/风险表；(10) commit `e704577`；**498 passed + 1 skipped + 68 E2E**（零回归）；未配置 key 时零成本回退到 worldcup26.ir |
| 2026-06-17 | **v0.14.1** | **数据质量校验层（去重/时效/状态机/优先级）**：(1) 新增 `app/services/data_quality.py` — `deduplicate` / `assert_unique` / `is_fresh` / `validate_kickoff_window` / `is_status_transition_allowed` / `can_overwrite` / `source_quality_summary`；(2) `app/services/api_football_sync.py` 接入：fixtures 去重 + 时间窗口校验 + 状态机保护 + 源优先级覆盖；(3) `app/services/worldcup26_sync.py` 接入：teams/stadiums/matches/standings/events 全链路去重 + 优先级保护 + 状态机；(4) `app/services/multi_source_sync.py` 新增 `_api_football_quality_ok()`：重复率 >5% 或 not_found >50 自动降级；(5) 新增 `tests/test_data_quality.py` 25 单元测试；(6) 更新 README 测试数与 v0.14.1 banner |
| 2026-06-17 | **v0.14.2** | **Cockpit / 赛事总览驾驶舱去重 redesign**：(1) 新增 `app/services/cockpit.py` 聚合服务 + `app/routers/cockpit.py` `GET /api/cockpit/summary`；(2) 前端 `app/static/js/app.js` `renderCockpit` 重写为“统计 + 总预览 + 互联互通”，含赛事进度/KPI/数据健康/晋级总览/未来 72h 关键战/模型共识/市场-模型分歧/Elo Top 5/快速入口；(3) 更新 E2E：`tests/e2e/test_cockpit_e2e.py` 2 项 + `tests/e2e/test_forward_testing_e2e.py` 移除旧 cockpit mini-card、改测 `/#/accuracy` + 版本断言；(4) `tests/e2e/test_weight_sweep_e2e.py` 适配新版快速入口；(5) `app/static/sw.js` 缓存版本升 `wc2026-v2`，`index.html` 静态资源加 `?v=0.14.2` 防旧版缓存；(6) `app/main.py` 版本号改为显式常量 `0.14.2`（支持 `WC26_VERSION` 环境覆盖）；(7) `app/services/simulator.py` `simulate_group_advancement` 支持 `n_sims` 参数，Cockpit 用 1000 次降低延迟；(8) `tests/e2e/conftest.py` 禁用 Service Worker + 预加载加 nocache，避免 E2E 拿到旧版 app.js；(9) 修复 `tests/test_prediction_log_lifespan.py::test_run_periodic_refresh_includes_predictions_step` 因外部同步引入额外比赛导致的 flaky；(10) **494 passed, 1 skipped + 69 E2E 全绿** |
