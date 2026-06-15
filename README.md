# 2026 FIFA World Cup 赛事分析平台 · 工程交付

> **文档版本**：v0.2.0（数据完整性 + 时区现代化 audit 修复，2026-06-15 08:20）
> **阶段**：Phase 5 – Ship（v0.2 收尾 + 全量 audit）
> **作用域**：48 强全量赛程 + worldcup26.ir 实时同步 + Elo-Poisson v2（含 form/H2H）+ 出线模拟器 + 手动兜底 + CSV 导出 + 历史交锋详情页

---

## 一、范围与定位

### 1.1 范围（v0.2 已交付）

| 已交付 | 范围 |
|---|---|
| ✅ 静态 H5 前端（中文、深色） | 首页/赛程/积分榜/球队/比赛详情/Elo 实力榜/历史交锋/出线模拟器；Tailwind + 移动优先；hash SPA |
| ✅ 后端 API（FastAPI · 31 端点） | matches (4) / teams (4) / groups / predictions (2) / elo (6) / h2h (2) / simulator / admin (11) / health |
| ✅ Elo-Poisson v2 预测 | M1 纯 Elo + Dixon-Coles + M2 增强（form + H2H 加权因子），双返回 v1/v2 |
| ✅ 出线模拟器 | `/api/simulator/groups` + 前端交互式界面（v0.2 提前交付，原计划 v0.3+）|
| ✅ CSV 导出 | Elo 页 "导出 CSV" 按钮（48 队全榜 + 10 字段 + UTF-8 BOM）|
| ✅ 历史交锋详情页 | 路由 `#/h2h/{code1}/{code2}` + 视角归一 + 9 队非参赛队 fallback |
| ✅ 数据导入 | worldcup26.ir 实时同步（每 15min 调度 + 启动时立即同步）+ worldcupstats.football 备份 + 手动兜底 |
| ✅ 手动管理接口 | 8 端点（比分/事件/统计/积分榜手动/同步触发/缓存失效/form 回填/team recent-form），需 `X-Admin-Token` |
| ✅ 比赛详情 | events / stats / 赛后复盘卡片（B4）/ weather |
| ✅ 自动化测试 | **95 项**单元 + 集成测试，全部通过 |

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
│   │   ├── admin.py         # 4 端点（比分/事件/统计/积分榜手动）
│   │   └── admin_sync.py    # 4 端点（同步状态/触发/缓存失效/form 回填）
│   ├── services/
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
Admin POST (X-Admin-Token) ──→ admin.py + admin_sync.py
                          ↓
                   FastAPI API (31 端点)
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

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

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

## 六、API 速查（v0.2 共 31 端点，含 /health）

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

### 6.2 Elo + 预测 API（M1 + M2）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/elo/ratings` | 48 队 Elo 评分 |
| GET | `/api/elo/ratings/{FIFA}` | 单队评分 |
| GET | `/api/elo/top?limit=10` | Top N |
| GET | `/api/elo/predict/{home}/{away}` | 1v1 预测（v1 纯 Elo + Dixon-Coles）|
| GET | `/api/elo/predict-enhanced/{home}/{away}` | v1 + v2 双返回（form + H2H 增强）|
| GET | `/api/elo/backtest` | 4 年 walk-forward 回测指标 |
| GET | `/api/predictions/cache/stats` | 缓存统计（命中率/总条数）|

### 6.3 H2H + 模拟器

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/h2h/{code1}/{code2}` | 两队所有直接对决 + 胜负条（视角归一）|
| GET | `/api/simulator/groups` | 出线模拟器（基于当前 standings）|

### 6.4 管理 API（需 `X-Admin-Token`）

**6.4.1 数据手动维护**（前缀 `/api/admin/`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/admin/matches/{id}/score` | 手动更新比分 |
| POST | `/api/admin/matches/{id}/events` | 手动录入事件 |
| POST | `/api/admin/matches/{id}/stats` | 手动录入赛后统计 |
| POST | `/api/admin/standings/{group_name}` | 手动录入积分榜 |

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

## 八、风险与监控

| 风险 | 状态 | 兜底 |
|---|---|---|
| API-Football 100 次/天不够 | 🟡 未启用 | worldcupstats.football 爬虫 + 人工兜底 |
| worldcupstats 抓取失败 | 🟢 已实现降级 | 抓取失败时显示空列表，admin 手动录入 |
| 数据源频繁变化 | 🟡 无监控 | v0.2 加邮件/企业微信告警 |
| 预测偏差大 | 🟢 已声明免责 | UI 显示"仅供参考，不构成投注建议" |

---

## 九、下一阶段（v0.2）

1. **API-Football 实时层**（配置 Key 后启用）+ 配额监控
2. **WebSocket 推送**（轻量 SSE 替代）
3. **PWA 离线缓存**（赛前 1h 下载比赛包）
4. **Open-Meteo 天气集成**（按球场坐标）
5. **球员 360° 档案**（手动 + Transfermarkt 自托管）
6. **xG 数据接入**（StatsBomb Open Data 历史训练）

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
