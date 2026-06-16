# 2026 FIFA World Cup 赛事分析平台 · 工程交付

> **文档版本**：v0.6.0（准确率 dashboard + 3 模型横评 + 历史回填，2026-06-16）
> **阶段**：Phase 5 – Ship（v0.6.0 模型对比 + 偏差分析）
> **作用域**：48 强全量赛程 + worldcup26.ir 实时同步 + Elo-Poisson v2（含 form/H2H）+ **StatsBomb 双数据源对比** + 出线模拟器 + Bracket 淘汰赛路线图 + **市场赔率模块 M3（管理员手动录入 + value bet 算法）** + 手动兜底 + CSV 导出 + 历史交锋详情页

---

## 一、范围与定位

### 1.1 范围（v0.5.0 已交付）

| 已交付 | 范围 |
|---|---|
| ✅ 静态 H5 前端（中文、深色） | 首页/赛程/积分榜/球队/比赛详情/Elo 实力榜/历史交锋/出线模拟器/Bracket 晋级路线图/赔率分析；Tailwind + 移动优先；hash SPA |
| ✅ 后端 API（FastAPI · 40 端点） | matches (4) / teams (3) / groups (1) / predictions (2) / elo (7) / h2h (2) / simulator (1) / bracket (1) / **odds (3) · M3** / admin (4) / admin_sync (7) / **admin_odds (3) · M3** / health |
| ✅ Elo-Poisson v2 预测 | M1 纯 Elo + Dixon-Coles + M2 增强（form + H2H 加权因子），双返回 v1/v2；v0.4.0 新增 StatsBomb 数据源切换 + Hicruben/StatsBomb 预测对比 |
| ✅ 市场赔率模块 M3 | match_odds 表 + 3 个 admin 录入端点（单条/批量/删除）+ 3 个公开查询端点（单场赔率/赔率 vs Elo 对比/价值投注 TOP N）+ value bet 算法（模型概率 / 市场隐含概率 - 1）+ 前端 3 处接入（matchCard 角标 / match detail 详情卡 / 独立 `/#/odds` 页面） |
| ✅ 出线模拟器 | `/api/simulator/groups` + 前端交互式界面 |
| ✅ Bracket 淘汰赛路线图 | `/api/bracket` 自动计算 32 强（12 组前 2 + 8 个最佳第三）+ 16 场 R32 对阵 + Elo 胜率预测；`#/bracket` 真实数据渲染 |
| ✅ CSV 导出 | Elo 页 "导出 CSV" 按钮（48 队全榜 + 10 字段 + UTF-8 BOM）|
| ✅ 历史交锋详情页 | 路由 `#/h2h/{code1}/{code2}` + 视角归一 + 9 队非参赛队 fallback |
| ✅ 数据导入 | worldcup26.ir 实时同步（每 15min 调度 + 启动时立即同步）+ worldcupstats.football 备份 + 手动兜底 + 赔率 admin 录入 |
| ✅ 手动管理接口 | 14 端点（比分/事件/统计/Bracket 重建/同步触发/缓存失效/form 回填/H2H 回填/备份源调度/回测运行/**赔率 3 端点**），需 `X-Admin-Token` |
| ✅ 比赛详情 | events / stats / 赛后复盘卡片（B4）/ weather / **赔率卡（去 vig 市场概率 + 价值投注高亮）** |
| ✅ 自动化测试 | **193 项**单元 + 集成（**+41 M3**）+ **11 项** Playwright E2E（**+4 M3**），全部通过 |

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
│   ├── models.py            # ORM（teams/stadiums/matches/events/stats/standings/api_usage_log/prediction_cache/team_elo_ratings/h2h_historical_matches/team_recent_form）
│   ├── schemas.py           # Pydantic IO 模型
│   ├── routers/
│   │   ├── matches.py       # 5 端点
│   │   ├── teams.py         # 3 端点（team_code 兼容 ID + fifa_code）
│   │   ├── groups.py        # 1 端点
│   │   ├── predictions.py   # 2 端点（基础 + cache stats）
│   │   ├── elo.py           # 6 端点（ratings/top/predict/predict-enhanced/backtest）
│   │   ├── h2h.py           # 2 端点（对决详情 + 队所有对手）
│   │   ├── simulator.py     # 1 端点（出线模拟）
│   │   ├── bracket.py       # 1 端点（GET /api/bracket）
│   │   ├── admin.py         # 5 端点（比分/事件/统计/积分榜手动/Bracket 重建）
│   │   └── admin_sync.py    # 4 端点（同步状态/触发/缓存失效/form 回填）
│   ├── services/
│   │   ├── bracket_logic.py # 2026 淘汰赛对阵生成（小组排名/最佳第三/R32 对阵/Elo 预测）
│   │   ├── prediction.py    # Elo-Poisson v1 基础
│   │   ├── prediction_cache.py  # F2 缓存层
│   │   ├── backtest.py      # M1 4 年 walk-forward 回测
│   │   ├── elo.py           # M1 Elo + Dixon-Coles + M2 form/H2H 增强
│   │   ├── h2h_backfill.py  # 2018+2022 世界杯种子回填（111 场）
│   │   ├── recent_form.py   # B2 form 回填
│   │   ├── worldcup26_sync.py  # worldcup26.ir 全量同步（含 wc26_id → fifa_code 映射）
│   │   └── scheduler.py     # APScheduler 调度（每 15min 全量同步 + 每 30min B2 form 回填）
│   └── static/
│       ├── index.html       # H5 SPA 入口（抽屉 + 6 大模块路由）
│       ├── css/styles.css   # 自定义样式（Tailwind 互补）
│       └── js/app.js        # 路由 + 渲染（renderElo / renderH2H / renderH2HDetail / renderCockpit 等 12+ 函数）
├── data/
│   ├── scraper.py           # worldcupstats.football 抓取
│   ├── seed.py              # 原始 JSON → SQLite
│   ├── elo_seed.py          # M1 Hicruben 913 场 Elo 种子
│   ├── h2h_seed.py          # 2018+2022 世界杯 111 场 H2H 种子
│   ├── worldcup26.db        # SQLite（git 忽略）
│   └── fixtures/            # 抓取的原始 JSON
├── tests/
│   ├── conftest.py          # 临时 SQLite 隔离
│   ├── test_api.py
│   ├── test_api_integration.py
│   ├── test_cache.py
│   ├── test_elo.py
│   ├── test_enhanced_elo.py
│   ├── test_h2h.py
│   ├── test_simulator.py
│   └── test_prediction.py
├── scripts/                  # Playwright 端到端验证脚本
├── deliverables/             # 阶段交付报告（M1/M1.5/M2/P1.2/P1.3）
├── docs/screenshots/         # 截图归档
├── requirements.txt
├── .env                     # 本地配置（已 git 忽略示例）
└── README.md
```

### 2.1 数据流

```
worldcup26.ir (primary, 实时)
   ↓ /get/teams + /get/stadiums + /get/games + /get/groups
   ↓ wc26_id → fifa_code 映射（修 ID 错位）
   ↓
worldcup26_sync.py ──→ SQLite (48 队 + 16 球场 + 104 比赛 + 48 standings)
                          ↑
                          │ APScheduler 每 15min 增量 + lifespan startup 立即
                          │ B2 form 回填每 30min
                          │
worldcupstats.football (backup) ──→ scraper.py → fixtures/*.json → seed.py
                          ↑
API-Football (未启用)  ──→ 留 RAPIDAPI_KEY 配置位
                          ↑
StatsBomb Open Data ──→ scripts/download_statsbomb.py / build_statsbomb_from_extracted.py
   ↓ 309 场国际大赛 → train_statsbomb_elo() → data/seed/statsbomb/statsbomb_elo.json
   ↓（Hicruben 保持默认主模型；StatsBomb 作为可切换对比源）
Admin POST (X-Admin-Token) ──→ admin.py + admin_sync.py
                          ↓
                   FastAPI API (32 router 端点 + /health)
                          ↓
                   H5 SPA (app.js · 12+ 渲染函数 · hash 路由)
                          ↑
                   User (Web / Mobile 375px)
```

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

`.env` 示例：

```ini
ADMIN_TOKEN=worldcup2026-admin
RAPIDAPI_KEY=                       # API-Football 留空则跳过实时拉取
RAPIDAPI_HOST=api-football-v1.p.rapidapi.com
SYNC_INTERVAL_SECONDS=60
API_FOOTBALL_DAILY_LIMIT=100
APP_NAME=2026 FIFA World Cup 赛事分析平台
DEBUG=true
DATABASE_URL=sqlite:///./data/worldcup2026.db
```

> ⚠️ 生产部署务必修改 `ADMIN_TOKEN` 与 `DEBUG=false`。

---

## 五、Schema 迁移（Alembic）

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

**当前迁移链**（共 3 个）：
1. `aeaf6e483292` — init baseline（基线 + 补缺失索引）
2. `d7d93b3ec71e` — F2 `prediction_cache.factors_breakdown`
3. `ae0ea4ea9892` — M1 `team_elo_ratings` 表

详细报告见 [`deliverables/T1_alembic_completion_report.md`](deliverables/T1_alembic_completion_report.md)。

---

## 六、API 速查（v0.5.0 共 40 端点，含 /health）

### 6.1 核心数据 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 + 数据源 + 同步间隔 |
| GET | `/api/matches` | 全部比赛，支持 `?date=YYYY-MM-DD&group=A&status=live` |
| GET | `/api/matches/today` | 今日比赛（北京时间），进行中置顶 |
| GET | `/api/matches/{id}` | 单场详情（含 events/stats/赛后复盘）|
| GET | `/api/matches/{id}/weather` | 比赛天气（Open-Meteo）|
| GET | `/api/matches/{id}/prediction` | Elo-Poisson v1 预测（基础）|
| GET | `/api/teams` | 48 强列表 |
| GET | `/api/teams/{team_code}` | 球队详情（兼容 int ID + FIFA 3 字母代码 + 大小写不敏感）|
| GET | `/api/teams/{team_code}/matches` | 球队赛程（team_code 同上）|
| GET | `/api/teams/{team_code}/h2h-opponents` | 该队所有历史交锋对手（P2 用）|
| GET | `/api/groups` | 12 小组积分榜（wc26.ir 同步，已比赛自动汇总）|

### 6.2 Bracket 淘汰赛 API（v0.3.0）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bracket` | 完整淘汰赛对阵树（R32/R16/QF/SF/3rd/Final）+ Elo 预测概率 |
| POST | `/api/admin/bracket/rebuild` | 手动触发 Bracket 重算并持久化到 matches 表（需 admin token）|

### 6.3 Elo + 预测 API（M1 + M2 + v0.4.0 StatsBomb）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/elo/ratings?source=hicruben\|statsbomb` | 48 队 Elo 评分（默认 hicruben）|
| GET | `/api/elo/ratings/{FIFA}?source=...` | 单队评分 |
| GET | `/api/elo/top?limit=10&source=...` | Top N |
| GET | `/api/elo/predict/{home}/{away}?source=...` | 1v1 预测（v1 纯 Elo + Dixon-Coles）|
| GET | `/api/elo/predict-enhanced/{home}/{away}?source=...` | v1 + v2 双返回（form + H2H 增强）|
| GET | `/api/elo/compare/{home}/{away}` | **并排对比** Hicruben vs StatsBomb 预测 |
| GET | `/api/elo/backtest` | 4 年 walk-forward 回测指标（Hicruben）|
| GET | `/api/predictions/cache/stats` | 缓存统计（命中率/总条数）|

### 6.3 H2H + 模拟器 + 赔率（v0.5.0 M3）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/h2h/{code1}/{code2}` | 两队所有直接对决 + 胜负条（视角归一）|
| GET | `/api/simulator/groups` | 出线模拟器（基于当前 standings）|
| GET | `/api/matches/{id}/odds` | **M3** 单场赔率（各 bookmaker + consensus 平均 + 去 vig 市场概率）|
| GET | `/api/odds/compare` | **M3** 所有未完赛比赛：赔率(consensus) vs Elo 概率 + value bet |
| GET | `/api/odds/value-bets?min_rate=0.05` | **M3** 价值投注 TOP N（best_value_rate ≥ 阈值）|

### 6.4 管理 API（需 `X-Admin-Token`）

**6.4.1 数据手动维护**（前缀 `/api/admin/`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/admin/matches/{id}/score` | 手动更新比分 |
| POST | `/api/admin/matches/{id}/events` | 手动录入事件 |
| POST | `/api/admin/matches/{id}/stats` | 手动录入赛后统计 |
| POST | `/api/admin/standings/{group_name}` | 手动录入积分榜 |
| POST | `/api/admin/bracket/rebuild` | 手动触发 Bracket 重算（v0.3.0）|
| POST | `/api/admin/odds` | **M3** 手动录入单条赔率（同 match_id+bookmaker 覆盖）|
| POST | `/api/admin/odds/batch` | **M3** 批量录入赔率（含失败明细）|
| DELETE | `/api/admin/odds/{id}` | **M3** 删除单条赔率 |

**6.4.2 数据同步 + 缓存**（前缀 `/api/admin/sync/`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/sync/status` | 同步状态（最后同步时间/错误）|
| POST | `/api/admin/sync/worldcup26/full` | 手动触发 worldcup26.ir 全量同步 |
| POST | `/api/admin/sync/recent-form/backfill` | 触发 B2 recent_form 回填 |
| POST | `/api/admin/sync/stadium-coords/fill` | 补球场经纬度（Open-Meteo）|
| POST | `/api/admin/sync/h2h/backfill` | 触发 H2H 种子回填（2018+2022 世界杯）|
| POST | `/api/admin/sync/worldcupstats/schedule` | 触发 worldcupstats 抓取（备份源）|
| POST | `/api/admin/sync/backtest/run` | 触发 M1 4 年 walk-forward 回测 |

### 6.5 手动更新示例

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

**4 年 walk-forward 回测**（burn-in 150 场 + 评估 763 场）：

| 指标 | 我们的实现 | 投币基线 | 提升 |
|------|------------|----------|------|
| Ranked Probability Score (↓) | **0.2002** | 0.241 | **-17%** |
| Log-loss (↓) | **0.9690** | 1.10 | **-12%** |
| Brier score (↓) | **0.5752** | 0.67 | **-14%** |
| 准确率 (↑) | **58.3%** | 33% | **+77%** |
| 期望校准误差 | 11.75% | - | （10 段分箱偏粗） |

**48 队 Elo 评分 Top 10**：ESP 2010 / FRA 2009 / ENG 1993 / ARG 1976 / BRA 1955 / POR 1945 / GER 1926 / ITA 1901 / NED 1894 / NOR 1880

**5 个新 API 端点**：

```bash
GET /api/elo/ratings                  # 48 队评分
GET /api/elo/ratings/{FIFA}           # 单队评分
GET /api/elo/predict/{home}/{away}    # 1v1 预测
GET /api/elo/top?limit=10             # Top N
GET /api/elo/backtest                 # 4 年回测指标
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
| API-Football 100 次/天不够 | 🟡 未启用 | worldcupstats.football 爬虫 + 人工兜底 |
| worldcupstats 抓取失败 | 🟢 已实现降级 | 抓取失败时显示空列表，admin 手动录入 |
| 数据源频繁变化 | 🟡 无监控 | v0.2 加邮件/企业微信告警 |
| 预测偏差大 | 🟢 已声明免责 | UI 显示"仅供参考，不构成投注建议" |

---

## 九、下一阶段（v0.5.2+）

1. **历史赔率回测**（用 2018-2024 历史赔率做 Elo vs 市场历史胜率对比）
2. **付费赔率 API 接入**（oddsapi.com / pinnacle 商业 feed，让走势曲线出现真实波动）
3. **PWA 离线缓存**（赛前 1h 下载比赛包）
4. **球员 360° 档案**（手动 + Transfermarkt 自托管）
5. **xG 数据接入**（基于 StatsBomb Open Data event 数据做射门质量建模）

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
