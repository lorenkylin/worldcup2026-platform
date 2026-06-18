# 2026 FIFA World Cup 平台 — 项目进展与下步工作计划

> 整理日期: 2026-06-17 18:30 GMT+8
> 基于真实仓库状态: git HEAD `e704577`, tag `v0.13.0`
> 整理人: 奴才

---

## 一、当前状态总览

| 维度 | 状态 |
|---|---|
| **最新 tag** | `v0.13.0` (commit `e704577`) |
| **工作树改动** | 本次整理产生的文档 + 代码修复（未 commit） |
| **后端端点** | 61 个 router 端点 + `/health` = **62 个端点** |
| **非 E2E 测试** | **443 passed, 1 skipped** |
| **E2E 测试** | **65 passed** |
| **数据模型** | 17 张表，主数据齐全 |
| **前端页面** | 9+ 个 hash 路由（首页/teams/matches/elo/h2h/simulator/bracket/accuracy/odds/cockpit） |
| **部署** | Docker + docker-compose + Fly.io 一键部署就绪 |

---

## 二、版本里程碑（已发布）

### v0.10.0 · Observability 观测能力 + 数据新鲜度
- `data/sync_status.json` 持久化同步状态
- `/health` 增强：freshness + DB 行数 + scheduler 状态
- `/api/health/sync-status` 公开端点
- commit `d663535`, tag `v0.10.0`

### v0.11.0 · Forward-Testing 真 forward 准确率
- `prediction_log.is_live` + `snapshot_group`
- `/api/elo/live-accuracy` + `/api/elo/live-window-accuracy`
- Cockpit live accuracy mini-card
- commit `c6431db`, tag `v0.11.0`

### v0.12.0 · Deployment Infra 部署基础设施
- Dockerfile / .dockerignore / docker-compose.yml / deploy.sh
- `.github/workflows/ci.yml` 自动测试
- `tests/test_v012_deployment.py` 34 个部署断言
- commit `33f3806`, tag `v0.12.0`

### v0.12.1 · CI YAML 稳定性修复
- 修复 ci.yml 中文半角冒号导致 YAML 解析失败
- 新增 ci.yml / docker-compose.yml 真解析测试
- commit `1cf0836`, tag `v0.12.1`

### v0.13.0 · Fly.io 公网一键部署
- `fly.toml` + `deploy_fly.sh` + `fly_secrets_set.sh` + `migrate_data_to_fly.sh`
- `DATA_DIR` 环境变量支持本地 `./data` 与 Fly `/data`
- `/health` version 动态读取 git tag，防止漂移
- 时区与数据完整性 hotfix：UTC 存储 + 北京时间展示 + mock 赔率 seed
- commit `e704577`, tag `v0.13.0`

---

## 三、本次整理修复的问题

### 1. ✅ `/health` 版本号动态化
- 旧：`app/main.py` 写死 `version="0.13.0"`，后续 tag 漂移风险
- 新：`_get_version()` 从 `git describe --tags --always` 读取，fallback 到 `"0.13.0"`
- 验证：本地启动后 `/health` 返回 `"version": "0.13.0"`

### 2. ✅ 赛事时间统一为北京时间
- DB 统一存 UTC，API/前端统一按 `Asia/Shanghai` 展示
- `data/seed.py` 剥离 fixture 错误偏移，按球场真实时区转 UTC
- `app/routers/matches.py` 日期过滤改为北京时间语义
- `app/schemas.py` `MatchOut` 序列化为 `+08:00` ISO-8601
- `app/static/js/app.js` 移除 stadium-timezone 重建，统一用 `Asia/Shanghai`

### 3. ✅ E2E 赔率页数据稳定性
- `data/seed.py` 新增 `seed_mock_odds()`：所有比赛写入 MatchOdds，match_id=1 写入历史快照
- E2E 赔率 / 走势页不再依赖外部同步即有数据

### 4. ✅ 数据完整性回归测试
- 新增 `tests/test_data_integrity.py`：48 队 / 48 积分榜 / 104 场 / 无 placeholder / 无 group_name='Z'

---

## 四、下步工作计划（待主人拍板）

| 候选 | 价值 | 预计工时 | 依赖 | 风险 |
|---|---|---|---|---|
| **A. The Odds API 真实响应解析** | 替代 mock 赔率，接入真实市场数据 | 3–4h | v0.13.0 | 中（team name → fifa_code 映射） |
| **B. Pinnacle 赔率接入** | 更高质量真实赔率 | 4–6h | A | 中（付费/限速） |
| **C. MarketBlend 三方加权** | Elo + G2 + 赔率动态权重 | 2–3h | A/B | 中 |
| **D. 赔率调度器自动刷新** | 每 6h 自动拉取真实赔率 | 1h | A | 低 |
| **E. README v0.13.0 整合** | 文档与当前代码/部署流程对齐 | 1–2h | 无 | 低 |

### 推荐顺序
1. **先 A** — 真实赔率解析是 B/C/D 的前提，改动集中在 `app/services/odds_api_client.py`
2. **再 D** — 把真实赔率接入现有 6h 周期刷新
3. **然后 E** — README 统一更新到 v0.13.0
4. **最后 B/C** — 付费源与三方加权模型

---

## 五、关键数据基线

### DB 行数（生产 DB 经 lifespan sync 后）

| 表 | 行数 | 说明 |
|---|---|---|
| teams | 48 | FIFA 2026 真实 48 队 |
| standings | 48 | 12 组 × 4 队 |
| matches | 104 | 72 小组赛 + 32 淘汰赛 |
| stadiums | 16 | 北美 16 座球场 |
| prediction_log | 1+ | lifespan auto-log + 历史回填 |
| match_odds | 104+ | seed mock + 周期刷新 |
| odds_snapshots | 74+ | 走势数据 |

### API 端点清单（62 个）

| 模块 | 端点数 | 代表端点 |
|---|---|---|
| matches | 7+ | `/matches`, `/matches/today`, `/matches/{id}`, `/matches/{id}/odds`, `/matches/{id}/prediction` |
| teams | 3 | `/teams`, `/teams/{code}`, `/teams/{code}/matches` |
| groups | 1 | `/groups` |
| predictions | 2 | `/matches/{id}/prediction`, `/predictions/cache/stats` |
| elo | 10+ | `/elo/ratings`, `/elo/predict`, `/elo/live-accuracy`, `/elo/accuracy-stats` |
| odds | 7+ | `/odds/compare`, `/odds/value-bets`, `/odds/compare-model`, `/odds/service-status` |
| simulator | 2 | `/simulator/groups`, `/simulator/tournament` |
| h2h | 2 | `/h2h/{home}/{away}` |
| bracket | 1 | `/bracket` |
| health | 3 | `/health`, `/health/sources`, `/health/sync-status` |
| admin | 5+ | `/admin/matches/{id}/score`, `/admin/sync/...`, `/admin/odds/fetch` |
