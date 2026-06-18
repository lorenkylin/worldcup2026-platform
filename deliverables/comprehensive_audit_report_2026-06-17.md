# 2026 FIFA World Cup 平台 · 全面审计报告

> **审计日期**：2026-06-17  
> **审计范围**：`worldcup2026-platform/` 全仓库（代码、测试、部署、数据、文档）  
> **审计性质**：只读检查，未修改任何代码  
> **当前状态**：Git 工作区有已暂存但未提交的 v0.13.0 Fly.io 部署改动  

---

## 一、执行摘要

平台整体功能完整，核心服务（Elo/Glicko-2/Blend、数据同步、出线模拟、赔率、准确率）均可运行，`/health` 返回 healthy。但存在 **多个直接影响生产可用性的 bug** 和 **严重的文档/版本漂移**，在正式发布/部署前必须修复。

### 最关键的 5 个问题

| 优先级 | 问题 | 影响 |
|---|---|---|
| 🔴 P0 | `/api/odds/compare-model?model=glicko2` 返回 500 | 模型 vs 赔率对比在 Glicko-2 模式下崩溃 |
| 🔴 P0 | 前端 `/#/health` 页面因双 `/api` 前缀永久 404 | 数据源健康页无法使用 |
| 🔴 P0 | `fly.toml` 的 `release_command` 在 Fly.io 临时机上跑 alembic，不挂载持久卷 | 首次部署/迁移后 SQLite 结构不同步，可能导致数据丢失 |
| 🟠 P1 | `app/main.py` 版本号仍为 `0.11.0`，与 Dockerfile(`0.12.0`)、Fly 文件(`0.13.0`)、README 标题(`0.12.0`) 不一致 | `/health` 返回版本混乱，运维/用户困惑 |
| 🟠 P1 | `fly.toml` 用 `APP_DEBUG=false`，但 `config.py` 只识别 `DEBUG` | 生产环境可能仍以 `debug=True` 运行，暴露堆栈 |

---

## 二、版本与 Git 状态

### 2.1 版本号漂移（严重）

| 文件 | 声明版本 | 说明 |
|---|---|---|
| `app/main.py:116` | `0.11.0` | `/health` 实际返回 |
| `Dockerfile` 注释 | `v0.12.0` | — |
| `README.md` 标题 | `v0.11.0`（Forward-Testing）/ `v0.12.0`（Deployment Infra） | 双标题，本身已混用 |
| `fly.toml` / `deploy_fly.sh` / `fly_secrets_set.sh` / `migrate_data_to_fly.sh` / `docs/deployment/fly.io.md` | `v0.13.0` | 已暂存未提交 |

**建议**：统一 bump 到 `0.13.0`（因为 Fly 部署链已 ready 并暂存），或先 commit v0.13.0 再统一版本。

### 2.2 未提交改动

```bash
On branch master
Changes to be committed:
  modified:   .gitignore
  modified:   app/config.py          # DATA_DIR 支持
  new file:   deploy_fly.sh
  new file:   docs/deployment/fly.io.md
  new file:   fly.toml
  new file:   fly_secrets_set.sh
  new file:   migrate_data_to_fly.sh
  new file:   tests/test_v013_fly.py
```

状态干净（无未暂存改动），但 v0.13.0 工作未完成（版本号未 bump）。

---

## 三、API 端点审计

### 3.1 实际端点 vs README

- 实际挂载端点：**63 个**（含 `/`、`/health`）
- README §六 API 速查表基于 **v0.5.0**，大量端点未记录
- README 声明但**缺失**的端点：`POST /api/admin/standings/{group_name}`（手动录入积分榜）
- 实际存在但 README 未记录：Glicko-2/Blend/Adaptive/Weight Sweep/Live Accuracy、 odds v0.7.2、health 子端点 等 30+

### 3.2 已验证的关键 bug

#### 🔴 `/api/odds/compare-model?model=glicko2` 500 崩溃

**位置**：`app/services/model_odds_compare.py:57-61`

```python
if model == "blend":
    result = fn(home_code, away_code)
else:
    # elo / glicko2
    result = fn(home_code, away_code, db)
```

- `elo`：把 `db: Session` 当成 `source` 传入 `predict_match`。由于 `_get_team_elo_with_source` 只判断 `source == "statsbomb"`，会**静默回退到 hicruben**，不报错但忽略用户指定的 source。
- `glicko2`：`predict_outcome` 签名是 `(rating_a, rd_a, rating_b, rd_b, ...)`，传入球队代码字符串 + Session，直接 500。

**实测**：

```bash
curl "http://127.0.0.1:8000/api/odds/compare-model?match_id=1&model=glicko2"
# HTTP/1.1 500 Internal Server Error + 完整 traceback（debug 开启）
```

**建议**：在 `predict_match_with_model` 内按模型正确组装参数；elo 走 `predict_match(home, away)`，glicko2 先查 rating/RD 再调 `predict_outcome`。

#### 🟡 `/api/elo/predict` 多了未文档化的 `match_id` 参数

用于自动写 `prediction_log`，但 README 未说明。

---

## 四、前端 SPA 审计

### 4.1 已实现页面

README 声明的 9 大功能（Elo、1v1、H2H、Simulator、Bracket、Odds、Accuracy、Cockpit、CSV 导出）均已实现。

### 4.2 已验证的关键 bug

#### 🔴 `/#/health` 页面 404

**位置**：`app/static/js/app.js` `renderHealth()`

```javascript
apiWithRetry('/api/health/sources')   // api() 会再拼 /api → 请求 /api/api/health/sources
```

应为 `/health/sources`（同 `renderCockpit` 正确写法）。

**实测**：`GET /api/api/health/sources` 返回 404。

#### 🟠 Bracket 淘汰赛节点跳转到错误比赛 ID

`renderBracketNodeReal()` 使用 `#/match/${m.match_number}`，但 `/api/matches/{id}` 期望的是数据库自增 `id`，不是 `match_number`。

**影响**：用户从 Bracket 点击 R16/R32 节点会 404。

**建议**：后端 `/api/bracket` 返回真实 `match.id`，或前端通过 `match_number` 查询。

#### 🟠 `renderError` 重试按钮丢失闭包

```javascript
onclick="(${retryFn.toString()})()"
```

对 `() => renderTeamDetail(id)` 等带局部变量的箭头函数，字符串化后 `id` 变成全局未定义，点击重试抛 `ReferenceError`。

**影响**：球队详情、历史交锋等页的重试按钮失效。

#### 🟠 Cockpit 模型横评区域重复渲染

`accuracy && accuracy.n_settled > 0` 时渲染一次有数据版本；外层 `accuracy ? ... : ''` 又渲染一次“暂无已结算预测”。同时缺少 `accuracy.by_model` 空值保护。

#### 🟡 其他

- Glicko-2 榜单链接用英文队名 `#/team/${r.team_name}`，但后端只接受 FIFA 代码或 ID → 404
- `renderAccuracy()` 多处直接 `.toFixed()`，后端字段缺失时会崩溃
- Cockpit weight sweep 区块末尾多一个 `</div>`
- Cockpit 时钟 interval 离开页面未清理

---

## 五、部署与基础设施审计

### 5.1 Docker / VPS 链（基本可用）

- Dockerfile：非 root (`appuser uid 1000`)、`EXPOSE 8000`、`--workers 1`、HEALTHCHECK ✅
- docker-compose.yml：端口/卷/环境变量映射正确 ✅
- `deploy.sh`：功能完整 ✅
- **问题**：`deploy.sh` 未显式执行 alembic，依赖 `Base.metadata.create_all`，长期可能导致 alembic 历史不一致

### 5.2 Fly.io v0.13 链（关键风险）

| 检查项 | 状态 | 说明 |
|---|---|---|
| app 名一致性 | ✅ | `wc2026-fifa-platform` |
| DATA_DIR / mounts | ✅ | `/data` |
| 端口一致性 | ✅ | 8000 |
| `test_v013_fly.py` | ✅ 33 passed | Fly 四件套测试通过 |
| `release_command = "alembic upgrade head"` | ❌ 关键设计缺陷 | Fly release_command 在**不挂载卷的临时机**运行，迁移不生效 |
| `APP_DEBUG=false` | ❌ | `config.py` 字段名为 `debug`，`APP_DEBUG` 被 `extra="ignore"` 静默忽略 |
| `DATABASE_URL` 可覆盖 `DATA_DIR` | ⚠️ | `.env.example` 默认 `sqlite:///./data/worldcup2026.db`，若作为 Fly secret 保留会写非挂载路径 |

### 5.3 CI / 测试

- `.github/workflows/ci.yml` 基本配置正确（Python 3.13、pytest、alembic 干跑）
- **严重**：`tests/test_v012_deployment.py` 在 Windows 上 **25 failed / 9 passed**
  - 根因：`Path.read_text()` 未指定 `encoding="utf-8"`，Windows 默认 `gbk`，而 Dockerfile/ci.yml/.dockerignore/deploy.sh 含 UTF-8 em-dash `—`
  - 这会导致本地 Windows 开发无法验证部署，Ubuntu CI 可能通过
- 全量 pytest 在 600s 超时未跑完（498 项），E2E 全部 ERROR（Playwright 未配置/浏览器未安装）

### 5.4 `.env.example` 严重滞后

包含已废弃字段：`RAPIDAPI_KEY`、`RAPIDAPI_HOST`、`API_FOOTBALL_DAILY_LIMIT`
缺失字段：`FOOTBALL_DATA_API_KEY`、`ODDS_API_KEY`、`DATA_DIR`、`WC26_BASE_URL`、`FOOTBALL_DATA_ENABLED`、`ODDS_API_ENABLED`、`ODDS_API_PROVIDER`

---

## 六、数据层与迁移审计

### 6.1 模型与迁移

- 实际模型：**14 张表**
- 实际迁移文件：**9 个**
- README §五 声明：**3 个**（严重过时）
- 迁移链单链无分支，upgrade/downgrade 完整

### 6.2 模型 vs 数据库漂移

| 表 | 模型期望 | 数据库实际 | 风险 |
|---|---|---|---|
| `prediction_log` | `is_live` 有索引 | 无索引 | `live-accuracy` 类查询全表扫描 |
| `mc_run_history` | 有 `ix_mc_run_history_id` 等单列索引 | 有复合索引 `ix_mc_run_history_lookup`，缺 `id` 索引 | autogenerate 可能生成错误迁移 |

### 6.3 数据库内容

| 表 | 行数 | 预期 | 说明 |
|---|---|---|---|
| `teams` | 96 | 48 | 含 seed + 同步数据，无 fifa_code 重复，但数量翻倍 |
| `stadiums` | 17 | 16 | 多 1 条 |
| `matches` | 105 | 104 | 多 1 条 |
| `standings` | 48 | 48 | ✅ |
| `prediction_log` | 1,863 | — | 全部 `is_live=0`，尚无真 forward 实时记录 |
| `odds_snapshots` | 78 | — | ✅ |
| `team_elo_ratings` | 48 | — | **无任何业务代码读取，死表** |
| `odds_api_cache` | 0 | — | 不在 `models.py` 中，孤儿表 |

### 6.4 数据同步

- `worldcup26_sync.py` 与模型字段匹配 ✅
- 同步结果计数（48/16/104）与 DB 实际行数（96/17/105）不一致，说明 seed 与 sync 数据并存但未去重/清理

---

## 七、核心服务逻辑审计

### 7.1 确认可用的服务

全部 26 个服务文件语法正确，无循环依赖，核心预测/同步/赔率服务实现良好。

### 7.2 关键逻辑 bug

| 严重程度 | 问题 | 位置 | 影响 |
|---|---|---|---|
| 🔴 | `model_odds_compare.predict_match_with_model` 对 `elo/glicko2` 传参错误 | `app/services/model_odds_compare.py:57-61` | `/api/odds/compare-model?model=glicko2` 500；elo 静默回退 hicruben |
| 🟠 | `adaptive_weight.walkforward_adaptive_validate` 用 `"完赛"` 过滤 | `app/services/adaptive_weight.py:141` | 数据库状态为 `"finished"`，验证永远查不到比赛 |
| 🟠 | `backtest.py` 与 README 4 年 walk-forward 回测声明严重不符 | `app/services/backtest.py` | README 的 RPS/LogLoss/Brier/Accuracy 指标并非由该服务计算；admin 触发的是 H2H 历史回测 |
| 🟡 | `prediction.py` 与 `monte_carlo.py` Elo→λ 参数不一致 | 两套参数 | 单场预测与 MC 模拟进球分布不一致 |
| 🟡 | `prediction_log.auto_log_predictions` 未使用 `snapshot_group` | `app/services/prediction_log.py` | README 提到的赛前 7d/3d/1d 快照组未实现 |
| 🟡 | `bracket_logic` 最佳第三分配为贪心近似 | `app/services/bracket_logic.py` | 非 FIFA Annex C 官方优先级，R32 对阵可能偏差 |
| 🟢 | `weather.py` 硬编码取 18:00 天气 | `app/services/weather.py:53` | 非 18:00 开球比赛天气不准 |

---

## 八、测试结果汇总

### 8.1 全量 pytest（含 E2E）

```bash
python -m pytest tests/ -v --tb=short
# 498 items collected
# 600s 超时未跑完
# E2E 全部 ERROR（Playwright 未安装/浏览器缺失）
# v0.12 部署测试 25 failed（Windows 编码问题）
# 单元/集成测试大部分 PASSED
```

### 8.2 单独测试

| 测试文件 | 结果 |
|---|---|
| `tests/test_v013_fly.py` | **33 passed** ✅ |
| `tests/test_v012_deployment.py` | **25 failed, 9 passed** ❌（Windows `gbk` 编码） |

### 8.3 运行环境异常

- 启动 uvicorn 的 traceback 显示 Python 3.13.12，而 `pytest` 显示 Python 3.11.5，存在多 Python 环境混用。
- 生产部署若使用不同 Python 版本/依赖，可能引入不可预期行为。

---

## 九、建议修复优先级

### 🔴 P0 — 发布前必须修复

1. **统一版本号**：`app/main.py` bump 到 `0.13.0`，与 Fly 文件、README 保持一致。
2. **修复 `/api/odds/compare-model?model=glicko2` 500**：按模型签名正确分发参数。
3. **修复前端 `/#/health` 404**：`renderHealth()` 中 `/api/health/sources` → `/health/sources`。
4. **修复 Fly.io `release_command` 与持久卷不兼容问题**：
   - 方案 A：去掉 `release_command`，改在 `lifespan` startup 中执行 alembic（但需幂等/单实例锁）
   - 方案 B：保留 `release_command` 但改为不依赖 SQLite 的轻量检查，数据库迁移在首次数据上传后由管理员手动触发
5. **修复 `fly.toml` `APP_DEBUG` 命名错误**：改为 `DEBUG=false`，或 `config.py` 兼容 `APP_DEBUG`。

### 🟠 P1 — 短期内必须修复

6. **更新 `.env.example`**：删除废弃 RapidAPI 字段，补充 FOOTBALL_DATA/ODDS/DATA_DIR 等字段。
7. **修复 `tests/test_v012_deployment.py` 编码问题**：所有 `read_text()` 加 `encoding="utf-8"`。
8. **修复 Bracket 节点跳转错误**：后端返回真实 `match.id` 或前端按 `match_number` 查询。
9. **修复 `renderError` 重试闭包丢失**：使用全局注册函数方式。
10. **修复 `adaptive_weight.walkforward_adaptive_validate` 状态字符串**：`"完赛"` → `"finished"`。
11. **补充 `prediction_log.is_live` 索引**：提升 live accuracy 查询性能。
12. **处理数据库重复/多余数据**：调查 `teams=96/stadiums=17/matches=105` 的根因并清理。

### 🟡 P2 — 建议优化

13. 更新 README §六 API 速查表，补充 v0.6–v0.11 新增端点。
14. 明确 `backtest.py` 与 README 4 年 walk-forward 回测的关系，避免文档误导。
15. 统一 `prediction.py` 与 `monte_carlo.py` 的 Elo→λ 参数，或文档说明差异。
16. 清理死表 `team_elo_ratings` 或接入业务逻辑；删除孤儿表 `odds_api_cache`。
17. 修复 Cockpit 模型横评重复渲染、weight sweep 多余 `</div>`、Glicko-2 榜单链接、Accuracy 空值防御等前端体验问题。
18. CI 增加 `docker build` / `flyctl validate` 冒烟测试。

---

## 十、总体结论

该平台功能覆盖完整、核心预测服务健壮，**已具备上线基础**，但当前版本号混乱、存在 1 个 API 500 bug、1 个前端页面完全不可用、Fly.io 部署链有数据丢失风险。建议在修复 P0/P1 问题后再进行生产部署或发布 v0.13.0。
