# 2026 FIFA World Cup 平台 — 生产部署就绪审计报告

> **审计日期**：2026-06-26
> **当前版本**：v0.16.3（commit `96aee2a`，master 分支干净，24 个 git tag）
> **审计人**：工程实践专家（工序达）
> **目的**：主人要求在生产部署前全面审阅代码库、架构文档和开发记录，列出关键信息清单与风险点

---

## ASSUMPTIONS（审阅前必须明确）

1. **"已全部完成开发"** 主人指的是 v0.16.3 标签版本（commit `96aee2a`）已发布，master 分支无未提交改动
2. **"生产环境部署"** 指 Fly.io 公网部署（路径 A），Docker/VPS/腾讯云作为备选保留
3. **数据** 已通过 `python data/seed.py` 或多源同步填充，SQLite 1.4MB
4. **测试基线** = `545 unit + 1 skipped + 56 E2E`（实测自 README §10 末条）
5. **第三方数据源** 默认全部关闭（API-Football / football-data.org / The Odds API 均未启用），零成本走 worldcup26.ir 主备份路线

> 若主人有不同假设，立即纠正再继续。

---

## 一、版本与代码现状（实测，非估算）

### 1.1 Git 状态

```
branch: master (clean, working tree clean)
HEAD:   96aee2a release(v0.16.3): 推荐比分 UI 醒目化
前 5 commits:
  96aee2a release(v0.16.3): 推荐比分 UI 醒目化
  7e05565 ui(prediction): 推荐比分展示使用鲜艳醒目样式
  9caac2e release(v0.16.2): 前端首选/次选比分展示优化
  5b30c86 ci(deploy): add Fly.io auto-deploy workflow on tag push  ← v0.16.2 后新增
  e6f8914 release(v0.16.1): score recommendation v2.1 + acceptance green
```

**24 个 tag**（按版本排序，从 v0.8.1 起）：
```
v0.16.3 / v0.16.2 / v0.16.1 / v0.16.0 / v0.15.0 / v0.14.3 / v0.14.2 / v0.13.0 /
v0.12.1 / v0.12.0 / v0.11.0 / v0.10.0 / v0.9.0 / v0.8.1 / v0.8.0
（早期 v0.7.x 系列省略）
```

### 1.2 真实代码规模（实测 grep）

| 维度 | 实测数 | README 自报 | 差异 |
|---|---|---|---|
| API 端点（router 装饰器） | **66** | 68 | -2（README 含已 sunset 的 `/elo/calibrated-predict/*` 410 端点） |
| 含 `/` + `/health` | **68** | 68 | ✓ 匹配 |
| Routers 文件 | 13 | 13 | ✓ |
| Services 文件 | **35** | 24 | **+11**（README 未更新 v0.14+ 新增） |
| Services 总行数 | 11,821 | - | - |
| Alembic 迁移 | **19** | 13 | **+6**（v0.16.x primary/secondary score + v0.14.x 系列） |
| 测试（unit） | **545** | 545 | ✓ |
| 测试（E2E） | **56** | 56 | ✓ |
| 运维脚本 | 30 | ~30 | ✓ |

### 1.3 端点清单（按 router 实测）

| Router | 端点数 | 主要端点 |
|---|---|---|
| `admin.py` | 4 | score / events / stats / bracket/rebuild |
| `admin_odds.py` | 3 | 单条/批量录入 + 删除 |
| `admin_sync.py` | 10 | sync/full + sync/live + sync/status + 9 个兼容端点（含 arbitration）|
| `bracket.py` | 1 | `/api/bracket` R32→Final 对阵 |
| `cockpit.py` | 1 | `/api/cockpit/summary` 总览聚合 |
| `elo.py` | **20** | ratings / predict / predict-enhanced / compare / backtest / predict-glicko2 / glicko2-ratings / glicko2-metrics / predict-blend / accuracy-stats / live-accuracy / live-window-accuracy / top-bias / weight-sweep / adaptive-weight / predict-market-blend / **calibrated-predict (410 Gone)** / **calibration-summary (410 Gone)** + 2 |
| `groups.py` | 1 | `/api/groups` |
| `h2h.py` | 2 | h2h/{code1}/{code2} + h2h-opponents |
| `health.py` | 3 | sources / sources/{id} / sync-status |
| `matches.py` | 4 | matches / matches/today / matches/{id} / matches/{id}/weather |
| `odds.py` | 10 | compare / value-bets / latest / compare-model / value-bets-model / service-status + 4 history |
| `predictions.py` | 2 | cache/stats + predict |
| `simulator.py` | 2 | groups + tournament |
| `teams.py` | 3 | teams + teams/{code} + teams/{code}/matches |

---

## 二、技术栈完整盘点

### 2.1 后端

| 组件 | 版本/规格 | 来源 |
|---|---|---|
| Python | **3.13**（slim-bookworm） | Dockerfile |
| Web 框架 | FastAPI 0.115.0 | requirements.txt |
| ASGI | uvicorn[standard] 0.32.0 | requirements.txt |
| ORM | SQLAlchemy 2.0.36 + Alembic 1.13.3 | requirements.txt |
| 配置 | pydantic 2.9.2 + pydantic-settings 2.6.1 | requirements.txt |
| 调度 | APScheduler 3.11.0（BackgroundScheduler，时区 Asia/Shanghai） | requirements.txt |
| HTTP 客户端 | httpx 0.27.2 + requests ≥2.31.0 | requirements.txt |
| 数据处理 | pandas 2.2.3 + openpyxl 3.1.5 | requirements.txt |
| HTML 解析 | beautifulsoup4 4.15.0 + lxml ≥5.0.0 | requirements.txt |

**核心特性**：
- lifespan startup 立即跑 `multi_source_full_sync` + `recent_form` + `h2h_backfill` + `periodic_refresh` + `auto_log_predictions`（5 步启动序列）
- 调度器注册 6 个任务（多源实时 / recent_form / bracket 自动 / 6h 周期 / 预测结算 / MC 缓存预热）

### 2.2 前端（H5 SPA，无框架）

| 组件 | 版本/规格 | 来源 |
|---|---|---|
| HTML | 单文件 `index.html` | app/static/ |
| CSS | Tailwind CDN + 自定义 styles.css（深空玻璃拟态 v0.15.0） | app/static/css/styles.css |
| JS | 原生 ES6（无 React/Vue），12+ 渲染函数 | app/static/js/app.js |
| 字体 | Inter + Noto Sans SC（国际 + 中文） | index.html |
| 图表 | Chart.js 4.4.0 CDN（赔率走势） | jsdelivr.net |
| Service Worker | sw.js（缓存版本 wc2026-v7） | app/static/sw.js |
| 路由 | hash router（11 路由：`/`, `/teams`, `/matches`, `/elo`, `/h2h`, `/simulator`, `/bracket`, `/cockpit`, `/odds`, `/accuracy`, `/health`） | app.js |

**亮点**：
- 深空玻璃拟态 UI（v0.15.0）：glass-card + glow-border + 微光边框 + 渐变标题条
- 推荐比分醒目化（v0.16.3）：amber 高亮首选 + emerald 高亮次选
- data-testid 全保留（E2E 测试零侵入）

### 2.3 数据库

| 项 | 值 |
|---|---|
| 引擎 | SQLite 3（单文件 1.4MB） |
| 路径 | `data/worldcup2026.db`（DATA_DIR env 可覆盖） |
| 外键 | 启用（`PRAGMA foreign_keys=ON`） |
| 模型 | 17+ 张表（teams/stadiums/matches/events/stats/standings/api_usage_log/prediction_cache/team_elo_ratings/h2h_historical_matches/prediction_log/match_odds/odds_snapshots/mc_run_history/api_usage_log 等） |
| 迁移 | Alembic 19 个版本（最新：`51373a2cff45_add_primary_secondary_score_fields.py` v0.16.x） |

**关键说明**：
- SQLite 单文件 + 单连接设计 → 容器必须 `--workers 1`，否则并发写锁冲突
- DB 存 UTC，API/前端统一按 `Asia/Shanghai` 展示
- 数据初始化两条路径：`python data/seed.py`（本地） 或 lifespan startup 自动灌数据（Fly 首次部署）

### 2.4 第三方数据集成（4 源 + 手动兜底）

| 数据源 | 类型 | 启用 | 频率 | 默认 |
|---|---|---|---|---|
| API-Football | 主源（实时） | `API_FOOTBALL_ENABLED` | 15min live + 6h full | ❌ 默认关闭 |
| worldcup26.ir | 备份（实时） | `WORLDCUP26_BASE_URL` | 15min live + lifespan startup | ✅ 默认启用 |
| football-data.org | 元数据增强 | `FOOTBALL_DATA_ENABLED` | 6h 周期 | ❌ 默认关闭 |
| The Odds API | 赔率 | `ODDS_API_PROVIDER=mock\|the_odds_api` | 6h 周期 | ✅ mock |
| StatsBomb Open Data | Elo 对比源 | 内置 313 场 JSON | - | ✅ Hicruben 主 |
| 手动 admin | 兜底 | `X-Admin-Token` | - | ✅ |

**关键限制**：
- API-Football 免费层 **100 req/天 + 10 req/min**，已内置 budget_alert.py 80%/95% 邮件/企微告警
- worldcup26.ir 无 key 直接抓
- 字段级仲裁：`manual > api-football > worldcup26.ir`，状态只允许 `scheduled → live → finished` 正向推进

### 2.5 CI/CD

| Workflow | 触发 | 任务 |
|---|---|---|
| `.github/workflows/ci.yml` | push master/PR/main/workflow_dispatch | test + slow + e2e + lint（4 job，10min timeout） |
| `.github/workflows/deploy.yml` | **push tag v*** 或 workflow_dispatch | test gate → flyctl deploy → 60s 健康检查 |

**新增**：5b30c86 在 v0.16.2 后添加 deploy.yml，实现 `git tag v0.16.x && git push origin v0.16.x` 触发自动部署。

---

## 三、部署架构盘点（4 套并行）

### 3.1 对比矩阵

| 维度 | A. Fly.io 自动 CI | B. Fly.io 手动 | C. Docker + VPS | D. 腾讯云 Lighthouse |
|---|---|---|---|---|
| **触发** | push tag | `./deploy_fly.sh` | `./deploy.sh` | `sudo bash deploy_tencentcloud.sh` |
| **入口** | fly.toml + Dockerfile | fly.toml + Dockerfile | docker-compose.yml | nginx + systemd + certbot |
| **HTTPS** | 自动 | 自动 | 需 Nginx + certbot | 自动（certbot --nginx） |
| **持久卷** | 1GB wc2026_data (hkg) | 同左 | `./data` 本地盘 | 本地盘 |
| **Web 进程** | uvicorn 1 worker | 同左 | uvicorn 1 worker | uvicorn (systemd) |
| **域名** | `wc2026-fifa-platform.fly.dev` | 同左 | 主人自带 | 主人自带（脚本填 DOMAIN） |
| **运维成本** | ⭐ 零 | ⭐ 零 | ⭐⭐ 中（VPS 维护） | ⭐⭐ 中 |
| **国内访问** | ⭐⭐⭐ hkg 区域最佳 | 同左 | ⭐⭐ 看线路 | ⭐⭐⭐ 直连 |
| **回滚** | `flyctl deploy --image :previous` | 同左 | docker compose 切旧 tag | systemctl 切旧版 |
| **主人操作复杂度** | ⭐⭐ 需 GitHub secret | ⭐⭐⭐ 一键 | ⭐⭐ 一键 | ⭐⭐ 改 DOMAIN + token |

### 3.2 Fly.io 配置详情（路径 A/B 共享）

| 配置项 | 值 | 来源 |
|---|---|---|
| app name | `wc2026-fifa-platform` | fly.toml:6 |
| 主区域 | `hkg` 香港 | fly.toml:10 |
| 持久卷 | `wc2026_data` 1GB → `/data` | fly.toml:34-37 |
| 端口 | 80 (force_https) + 443 | fly.toml:44-50 |
| 并发 | hard 50 / soft 25 | fly.toml:52-55 |
| 健康检查 | TCP 15s + HTTP /health 30s | fly.toml:58-69 |
| 部署策略 | rolling | fly.toml:77 |
| env | `DEBUG=false`, `SKIP_STARTUP_SYNC=true`, `TZ=Asia/Shanghai`, `DATA_DIR=/data` | fly.toml:17-26 |
| Dockerfile | python:3.13-slim-bookworm + gosu 降权 + entrypoint.sh | Dockerfile |
| 启动命令 | `/app/entrypoint.sh uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` | Dockerfile:48 |

---

## 四、生产部署关键信息清单

### 4.1 必填环境变量（主人必做）

| 变量 | 生产值 | 必填 | 说明 |
|---|---|---|---|
| `ADMIN_TOKEN` | ≥32 位随机字符串 | ✅ 必填 | 管理端点鉴权，泄露 = 可改比分/赔率 |
| `DEBUG` | `false` | ✅ 必填 | 关闭 Swagger/Redoc，避免泄露接口 |
| `CORS_ORIGINS` | 实际域名（如 `https://wc2026.example.com`） | ✅ 必填 | 生产不允许通配符 + credentials |
| `DATABASE_URL` | `sqlite:////data/worldcup2026.db` | 自动（fly.toml 覆盖） | Fly 通过 DATA_DIR=/data 自动覆盖 |
| `DATA_DIR` | `/data` | 自动（fly.toml 设） | 持久卷挂载点 |
| `SKIP_STARTUP_SYNC` | `true`（首次部署改 `false`） | 推荐 | 稳定后跳过启动全量同步 |
| `TZ` | `Asia/Shanghai` | 推荐 | 调度器时区 |

### 4.2 可选环境变量（强烈推荐配置）

| 变量 | 推荐值 | 说明 |
|---|---|---|
| `API_FOOTBALL_KEY` | api-sports.io 免费 token | 主源 + 备份双保险（100 req/天） |
| `API_FOOTBALL_ENABLED` | `true` | 启用 API-Football |
| `API_FOOTBALL_BUDGET_WARNING_THRESHOLD` | `0.80` | 80% 触发告警 |
| `API_FOOTBALL_BUDGET_CRITICAL_THRESHOLD` | `0.95` | 95% 触发告警 |
| `ALERT_EMAIL_SMTP_*` | 真实 SMTP 配置 | 预算告警邮件通知 |
| `ALERT_WECHAT_WEBHOOK_URL` | 企业微信机器人 | 预算告警企微通知 |
| `ODDS_API_PROVIDER` | `the_odds_api` | 真实赔率（500 req/月免费） |
| `ODDS_API_KEY` | The Odds API token | 启用真实赔率 |

### 4.3 GitHub Secrets（路径 A 必须）

| Secret | 用途 |
|---|---|
| `FLY_API_TOKEN` | Fly.io deploy workflow 鉴权（Read/Write 权限） |
| `ADMIN_TOKEN` | E2E 测试用 |

### 4.4 部署前数据准备

```bash
# 本地准备（双跑场景）
cd worldcup2026-platform
alembic upgrade head                    # 应用 19 个迁移
python data/seed.py                      # 写入 48 队 / 104 场 / 48 standings
python -m uvicorn app.main:app           # 触发 lifespan 自动同步

# 验证数据完整性
sqlite3 data/worldcup2026.db \
  "SELECT COUNT(*) FROM teams; \
   SELECT COUNT(*) FROM matches; \
   SELECT COUNT(*) FROM standings;"
# 期望：48 / 104 / 48

# 打包数据上传 Fly
./migrate_data_to_fly.sh                # 仅路径 B 需要
```

### 4.5 部署后验证清单

| 检查 | 命令 / 端点 | 期望 |
|---|---|---|
| 服务存活 | `curl https://wc2026-fifa-platform.fly.dev/health` | 200 + version=0.16.3 + scheduler_running=true |
| 数据源健康 | `curl .../api/health/sources` | overall=all_ok |
| 数据完整性 | `curl .../api/teams \| jq length` | 48 |
| | `curl .../api/matches \| jq length` | 104 |
| | `curl .../api/groups \| jq length` | 12 |
| 安全基线 | `curl .../api/docs` | 404（DEBUG=false 关闭） |
| | `curl .../api/admin/sync/status` 无 admin token | 403 |
| 前端资源 | 浏览器访问 `/` | 深空玻璃拟态 UI 正常渲染 |
| Service Worker | DevTools → Application → Service Workers | scope `/` 注册成功 |
| 移动端 | 375px 视口 | 底部 Tab 不挤压 |

---

## 五、潜在风险点（按严重度分级）

### 5.1 🔴 CRITICAL — 必须生产前修复（3 项）

| # | 风险 | 文件:行 | 实测值 | 应改为 |
|---|------|---------|--------|--------|
| 1 | **ADMIN_TOKEN 默认值未改** | `.env:4` | `your-secure-admin-token-change-me-in-production` | ≥32 位随机字符串（如 `openssl rand -hex 32`） |
| 2 | **DEBUG=true 泄露 Swagger/Redoc** | `.env:11` / docker-compose | `true` | `false`（生产必须关闭 `/api/docs` + `/api/redoc`） |
| 3 | **CORS 通配符 + 凭证** | `app/config.py:57-60` | `["*"]` 默认 | 实际域名白名单（如 `https://wc2026.example.com`） |

**威胁场景**：
- 风险 1 泄露：攻击者用 admin token 可改任何比赛比分/赔率/触发回测，数据完整性被破坏
- 风险 2 泄露：暴露全部 68 个端点文档，方便攻击者摸排
- 风险 3 泄露：通配符 + credentials 配置不当可能引发 CSRF + 凭证泄露

### 5.2 🟡 IMPORTANT — 强烈建议生产前修复（6 项）

| # | 风险 | 文件:行 | 现状 | 应改为 |
|---|------|---------|------|--------|
| 4 | **首次部署 SKIP_STARTUP_SYNC=false 让 lifespan 自动灌数据** | fly.toml:26 / .env | `true` | 首次部署临时改 `false`，稳定后改回 `true` |
| 5 | **API-Football 未启用** | .env / config | `API_FOOTBALL_ENABLED=false` | 启用 `true` + 配 key，可获主源 + 备份双保险 |
| 6 | **赔率 mock 模式** | `app/config.py:114` | `ODDS_API_PROVIDER=mock` | The Odds API 真实赔率（500 req/月免费） |
| 7 | **Fly.io GitHub secret 未配** | GitHub repo Settings | - | 配 `FLY_API_TOKEN` 后 `git tag v0.16.3 && git push origin v0.16.3` 触发自动部署 |
| 8 | **SQLite 多实例并发写锁** | fly.toml / docker-compose | 单进程 OK | 严禁 `--workers > 1`，已 fly.toml 设 `workers 1` |
| 9 | **teams 表 48 placeholder 遗留** | data/worldcup2026.db | 96 行（48 真实 + 48 占位）| 用 worldcup26.ir 重新 sync 覆盖（multi_source_sync 已支持去重） |

### 5.3 💭 SUGGESTION — 可选优化（5 项）

| # | 风险 | 说明 | 优先级 |
|---|------|------|--------|
| 10 | match_odds 仅 2 行（赔率录入稀疏） | 价值投注/走势曲线看不出真实波动 | P2 |
| 11 | matches 表有 1 场 group_name='Z' 异常 | 早期种子遗留 | P3 |
| 12 | v0.7.10 E2E mini-card 测试代码 | 已 sunset，无需修，仅 cleanup | P3 |
| 13 | 25 个 v0.12.0 deployment 测试 Windows 全量并发 flaky | 单跑全过，CI Linux 不受影响 | P3 |
| 14 | CORS allow_credentials 通配符自动禁用 | 已内置保护（`_cors_allow_credentials = ... and "*" not in ...`） | 已防护 |

### 5.4 已知架构约束（非风险，但需知）

| 约束 | 说明 |
|------|------|
| 单实例 SQLite | 无法横向扩展（加 worker 会冲突），如需高并发应迁移 PostgreSQL |
| Fly 免费 tier | 3 shared-cpu-1x 256MB 实例 + 1GB 持久卷，超过需付费 |
| lifespan 启动耗时 | 灌数据 20-30s，加上首次部署若 SKIP_STARTUP_SYNC=false，启动可能 60s+ |
| API-Football 100 req/天 | 15min 实时同步单次约 4-6 req → 96 req/天 接近上限 |
| worldcup26.ir 无 SLA | 备份源，挂了不影响功能但数据延迟 |

---

## 六、推荐生产部署路径

### 路径 A：Fly.io 自动部署（⭐ 推荐）

**适用场景**：主人零运维成本 + 公网 HTTPS + 国内 hkg 区域

**前置**：
1. 注册 fly.io 账号 + 绑卡（奴才不能做）
2. 获取 FLY_API_TOKEN（Read/Write 权限）
3. GitHub repo Settings → Secrets → 添加 `FLY_API_TOKEN`
4. 生产环境变量注入：`./fly_secrets_set.sh`（ADMIN_TOKEN ≥32 字符 + 可选 API_FOOTBALL_KEY）

**部署命令**：
```bash
cd worldcup2026-platform
# 1. 验证本地
pytest tests/ -m "not slow and not e2e" -v    # 必须全绿
git status                                     # 确认干净

# 2. 推 tag 触发自动 CI
git tag v0.16.3
git push origin v0.16.3

# 3. 等待 GitHub Actions 完成（test gate + deploy + 60s 健康检查）
# 4. 访问 https://wc2026-fifa-platform.fly.dev 验证
```

**时间**：从 `git push` 到可用约 **5-8 分钟**（test 1min + deploy 4min + health 1min）

### 路径 B：Fly.io 手动部署（备选）

适用：想在本地控制部署节奏的主人

```bash
export FLY_API_TOKEN=<your-token>
cd worldcup2026-platform
./deploy_fly.sh                              # 自动创建 app + 持久卷 + 部署
./fly_secrets_set.sh                         # 注入 ADMIN_TOKEN + 可选 keys
./migrate_data_to_fly.sh                     # 上传本地 SQLite（可选）
```

### 路径 C：Docker + VPS（已自带服务器的主人）

```bash
cd worldcup2026-platform
# 1. 编辑 .env：DEBUG=false + ADMIN_TOKEN ≥32 + CORS_ORIGINS=实际域名
./deploy.sh                                  # git pull + build + up + 60s 健康检查
```

### 路径 D：腾讯云 Lighthouse（国内最优）

```bash
# 1. 编辑 scripts/deploy_tencentcloud.sh 顶部 DOMAIN + ADMIN_TOKEN
# 2. sudo bash scripts/deploy_tencentcloud.sh
# 自动：系统更新 + Python venv + Nginx + certbot SSL + systemd
```

---

## 七、部署前最终检查清单（主人核对）

| 项 | 必做 | 操作 |
|---|------|------|
| ☐ | ✅ | `.env` 的 `ADMIN_TOKEN` 改为 ≥32 位随机 |
| ☐ | ✅ | `DEBUG=false` |
| ☐ | ✅ | `CORS_ORIGINS` 改为实际域名 |
| ☐ | ✅ | `SKIP_STARTUP_SYNC=false`（首次部署） |
| ☐ | ✅ | `git tag v0.16.3 && git push origin v0.16.3` |
| ☐ | ✅ | 等待 GitHub Actions 跑完（test gate → deploy → health check） |
| ☐ | ✅ | 浏览器访问 `/` + `/#/cockpit` + `/#/elo` + `/#/odds` 验证 UI |
| ☐ | ✅ | 移动端 375px 视口验证底部 Tab |
| ☐ | ✅ | `curl /health` 确认 `version=0.16.3` + `scheduler_running=true` |
| ☐ | ✅ | `curl /api/health/sources` 确认 overall=all_ok |
| ☐ | ✅ | （可选）`./fly_secrets_set.sh` 注入 API_FOOTBALL_KEY 启用主源 |
| ☐ | ✅ | （可选）`./migrate_data_to_fly.sh` 上传本地 1.4MB SQLite |

---

## 八、审计结论

### 项目就绪度：✅ **可生产部署**（修复 3 个 BLOCKER 后）

**优势**：
- 完整 4 套部署路径（Fly.io 自动 / 手动 / Docker / 腾讯云）
- CI/CD 已就绪（ci.yml 4 job + deploy.yml tag 触发）
- 容器化标准（python:3.13-slim-bookworm + 非 root + gosu 降权）
- 持久卷挂载设计正确（fly.toml DATA_DIR=/data + entrypoint.sh chown）
- 健康检查多层级（TCP + HTTP + DB 行数 + scheduler 状态）
- 多源编排 + 字段级仲裁（v0.14.x）保证数据质量
- API-Football 预算告警（v0.14.3）防止 100 req/天 耗尽

**必须修复**（3 项 BLOCKER）：
- ADMIN_TOKEN / DEBUG / CORS 三项仍是 dev 默认值，**生产前必改**

**强烈建议**（6 项 P1）：
- API-Football 主源未启用、赔率 mock 模式、Fly.io GitHub secret 待配

**风险可控**：架构设计已覆盖大部分常见风险（SQLite 单进程、Fly /data 权限、API-Football 预算、Sunset E2E 清理）

### 主人下一步建议

1. **修复 3 项 BLOCKER**（5 分钟）：编辑 `.env` 或用 `./fly_secrets_set.sh`
2. **配 Fly.io GitHub secret**（2 分钟）：Settings → Secrets → FLY_API_TOKEN
3. **推 tag 触发自动部署**（8 分钟）：`git tag v0.16.3 && git push origin v0.16.3`
4. **部署后验证**（5 分钟）：按 §四.4 部署后验证清单逐项核对
5. **观察 24h**：scheduler 跑几轮后看 `/api/health/sources` 数据源健康度

---

**报告人**：工序达
**审计用时**：约 25 分钟（实测 + grep + 读关键文件）
**总产出物**：1 份审计报告 + 2 份 memory 更新
**关联文件**：
- `deliverables/deployment_readiness_review_2026-06-26.md`（本文）
- `.workbuddy/memory/MEMORY.md`（已同步至 v0.16.3）
- `.workbuddy/memory/2026-06-26.md`（今日审计日志）