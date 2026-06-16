# 2026 FIFA World Cup 平台 — 项目进展与下步工作计划

> 整理日期: 2026-06-16 13:47
> 基于真实仓库状态: git HEAD `b17ddaf`, tag `v0.7.1`
> 整理人: 奴才

---

## 一、当前状态总览

| 维度 | 状态 |
|---|---|
| **最新 tag** | `v0.7.1` (commit `b17ddaf`) |
| **工作树改动** | `app/main.py` 1 处(版本号 0.6.0 → 0.7.1,未 commit) |
| **后端端点** | 49 个 `@router.*` + `/health` = **50 个端点** |
| **非 E2E 测试** | **291 passed, 1 skipped, 235.14s** (零回归) |
| **E2E 测试** | v0.7.1 新增 6 个,本次未跑(需服务启动) |
| **数据模型** | 15+ 表(Match/Team/Standing/Elo/Glicko2/PredictionLog/OddsSnapshot/...) |
| **前端页面** | 8 个 hash 路由(`/#/` 首页/teams/matches/elo/h2h/simulator/bracket/accuracy/odds) |

---

## 二、版本里程碑(已发布)

### v0.6.0 · 准确率 Dashboard + Glicko-2
- `PredictionLog` 表 + walk-forward 回填 913 场
- 4 个端点:`/elo/glicko2-ratings`、`/elo/glicko2-metrics`、`/elo/accuracy-stats`、`/elo/top-bias`
- `/accuracy` 3 模型对比表 + Cockpit mini-card
- **Glicko-2 62.65% vs Elo 56.63%(+6.02 pp)**
- 276 passed + 1 skipped, 15 E2E 全绿

### v0.7.0a · ModelBlend (Elo + Glicko-2)
- `/api/elo/predict-blend/{home}/{away}` 端点 + `predict_match_blend()` 服务
- match_id 可选写 prediction_log,权重校验 w_elo + w_glicko2 = 1.0
- 11 测试 + 5 E2E 数学验证到 4 位小数
- commit `844190a`, tag `v0.7.0a`

### v0.7.0b · Lifespan 自动写库 + 前端 3-tab
- `auto_log_predictions()` 服务 + 3 模型注册表
- `app/main.py` lifespan startup 立即跑一次 + 6h 周期刷新 step 3
- `app/static/js/app.js` 3-tab (elo/glicko2/blend)+ Glicko-2 评分榜折叠
- 8 集成测试 + 7 e2e
- commit `e9c6635`, tag `v0.7.0b`, 280 passed + 1 skipped

### v0.7.1 · Monte Carlo Tournament
- `app/services/monte_carlo.py` 整届 10000 次模拟(组赛 + R32 → F)
- 48×48 prob_matrix 预计算,10000 sims ≈ **4 秒**(预算 15s)
- `GET /api/simulator/tournament` 端点 + Simulator 页 MC section
- 11 unit/集成 + 6 e2e
- 实测生产数据: **FRA 13.1% / ESP 13.0% / GER 10.4%**
- commit `b17ddaf`, tag `v0.7.1`, 291 passed + 1 skipped(非 E2E)

---

## 三、本次整理发现的问题

### 1. ⚠️ `/health` 版本号与 tag 不一致(已修)
- `app/main.py:116` 仍写 `version="0.6.0"`,但 git tag 已是 `v0.7.1`
- 后果:`/health` 返回 `"version": "0.6.0"`,部署后健康检查撒谎
- 动作:已改为 `version="0.7.1"`
- 待决策:是否现在 commit + 重新移动 tag `v0.7.1`

### 2. ⚠️ v0.7.1 截图目录缺失
- `deliverables/v0.7.1_release.md` 提到截图归档,但 `docs/screenshots/v0.7.1/` 不存在
- 待决策:是否补 2-4 张 Simulator/MC 页面截图

### 3. ℹ️ E2E 未在本次验证
- 非 E2E 291 passed + 1 skipped 已确认
- E2E 需服务启动后跑,本次未跑(v0.7.1 release 中声称 6/6 e2e PASS)

---

## 四、下步工作计划(待主人拍板)

| 候选 | 价值 | 预计工时 | 依赖 | 风险 |
|---|---|---|---|---|
| **A. v0.7.1.1 MC 缓存** | 减少重复计算,10000 sims 不每次都跑 | 1.5h | v0.7.1 | 低 |
| **B. v0.7.2 赔率 API 集成** | Pinnacle/The Odds API,模型 vs 市场对比 | 4-6h | v0.7.1 | 中(付费/限速) |
| **C. v0.7.3 真 MarketBlend** | Elo + G2 + 赔率三方加权,训练动态权重 | 2.5h | B | 中 |
| **D. README v0.8.0 整合** | 文档大更新,整合 v0.7.0a/b/1 | 2h | 无 | 低 |
| **E. 补 v0.7.1 截图 + 版本号 commit** | 收尾 v0.7.1 ship 动作 | 0.5h | 无 | 低 |

### 推荐顺序
1. **先 E(收尾)** — 5 分钟 commit 版本号 + 移动 tag,补截图,让 v0.7.1 真正闭环
2. **再 A(MC 缓存)** — 低工时高价值,用户每次点 MC 按钮不用等 4s
3. **然后 B/C(赔率 API → MarketBlend)** — 这是 v0.7 主线最终目标
4. **最后 D(README)** — 等 v0.7.2/3 做完再统一写文档,避免重复改

---

## 五、关键数据基线

### API 端点清单(49 个路由 + /health)

| 模块 | 端点数 | 代表端点 |
|---|---|---|
| matches | 4 | `/matches`, `/matches/today`, `/matches/{id}`, `/matches/{id}/weather` |
| teams | 3 | `/teams`, `/teams/{code}`, `/teams/{code}/matches` |
| groups | 1 | `/groups` |
| predictions | 2 | `/matches/{id}/prediction`, `/predictions/cache/stats` |
| elo | 10 | `/elo/ratings`, `/elo/predict`, `/elo/predict-blend`, `/elo/accuracy-stats`, ... |
| h2h | 2 | `/h2h/{c1}/{c2}`, `/teams/{code}/h2h-opponents` |
| simulator | 2 | `/simulator/groups`, `/simulator/tournament` |
| bracket | 1 | `/bracket` |
| odds | 5 | `/matches/{id}/odds`, `/odds/compare`, `/odds/value-bets`, `/matches/{id}/odds/history`, `/odds/latest` |
| admin | 4 | `/matches/{id}/score`, `/matches/{id}/events`, `/matches/{id}/stats`, `/bracket/rebuild` |
| admin_odds | 3 | `/odds`, `/odds/batch`, `/odds/{id}` |
| admin_sync | 6 | `/worldcup26/full`, `/recent-form/backfill`, `/stadium-coords/fill`, `/h2h/backfill`, `/worldcupstats/schedule`, `/backtest/run`, `/status` |
| health | 2(+1) | `/sources`, `/sources/{id}`, `/health` |

### 测试基线

| 版本 | 单元/集成 | E2E | 总时长 |
|---|---|---|---|
| v0.6.0 | 276 passed + 1 skipped | 15 passed | ~4m25s |
| v0.7.0a | 280 passed + 1 skipped | 5 passed | ~4m19s |
| v0.7.0b | 280 passed + 1 skipped | 7 passed | ~3m04s |
| v0.7.1 | **291 passed + 1 skipped** | 6 passed(待本次验证) | ~3m55s(非 E2E) |

---

## 六、待主人决策

1. **是否现在 commit 版本号修复并移动 tag `v0.7.1`?**
2. **是否补 `docs/screenshots/v0.7.1/` 截图?**
3. **下一步优先做哪一项?** 推荐顺序:E → A → B/C → D
4. **v0.7.2 赔率 API 选哪个源?** Pinnacle(付费高质) / The Odds API(免费层有限) / 其他

主人下令,奴才推进。
