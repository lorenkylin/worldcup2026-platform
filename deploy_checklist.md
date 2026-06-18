# 2026 FIFA World Cup 平台 · 生产部署检查清单

> 适用版本：v0.15.0 及后续
> 目标环境：Fly.io / Docker / VPS

---

## 一、部署前准备

### 1.1 代码与版本

- [ ] 本地分支干净：`git status` 无未提交改动
- [ ] 目标 commit/tag 正确：`git log --oneline -3`
- [ ] 已打 tag（可选但推荐）：`git tag v0.15.0 && git push origin v0.15.0`

### 1.2 环境变量 `.env`

复制 `.env.example` 为 `.env`，并至少修改以下项：

| 变量 | 生产值要求 | 说明 |
|---|---|---|
| `DEBUG` | `false` | 关闭 Swagger/Redoc，避免泄露接口 |
| `ADMIN_TOKEN` | ≥32 位随机字符串 | 管理员敏感操作鉴权 |
| `SKIP_STARTUP_SYNC` | `true` | 避免每次部署全量同步外部源 |
| `CORS_ORIGINS` | 实际域名 | 生产不允许 `*` + credentials |
| `DATABASE_URL` | `sqlite:///./data/worldcup2026.db` | Fly.io 通过 `DATA_DIR=/data` 覆盖 |
| `DATA_DIR` | `./data` | Fly 持久卷挂载 `/data` |

### 1.3 数据源 Key（至少选一个主源）

- [ ] **API-Football 直接**：`API_FOOTBALL_ENABLED=true` + `API_FOOTBALL_KEY=<key>`
- [ ] **或 RapidAPI 代理**：先在 RapidAPI 订阅 API-Football，再填 `RAPIDAPI_KEY` + `RAPIDAPI_HOST=api-football-v1.p.rapidapi.com`
- [ ] **赔率（生产必选）**：`ODDS_API_ENABLED=true` + `ODDS_API_PROVIDER=the_odds_api` + `ODDS_API_KEY=<key>`
  - 若暂时无 key，保持 `ODDS_API_ENABLED=false`，前端会显示「模拟数据」提示

### 1.4 API-Football 预算告警（v0.14.3，可选但推荐）

若启用 API-Football 主源，建议同时开启预算告警，防止 100 req/天 免费额度耗尽导致同步降级：

| 变量 | 生产值要求 | 说明 |
|---|---|---|
| `API_FOOTBALL_BUDGET_WARNING_THRESHOLD` | `0.80` | 日用量 >= 80% 触发 warning |
| `API_FOOTBALL_BUDGET_CRITICAL_THRESHOLD` | `0.95` | 日用量 >= 95% 触发 critical |
| `ALERT_EMAIL_ENABLED` | `true` / `false` | 是否邮件告警 |
| `ALERT_EMAIL_SMTP_HOST` | `smtp.example.com` | SMTP 服务器 |
| `ALERT_EMAIL_SMTP_PORT` | `587` | SMTP 端口 |
| `ALERT_EMAIL_SMTP_USER` | `alert@example.com` | SMTP 账号 |
| `ALERT_EMAIL_SMTP_PASSWORD` | `<password>` | SMTP 密码 |
| `ALERT_EMAIL_FROM` | `alert@example.com` | 发件人 |
| `ALERT_EMAIL_TO` | `ops@example.com` | 收件人，支持逗号分隔多个 |
| `ALERT_WECHAT_ENABLED` | `true` / `false` | 是否企业微信告警 |
| `ALERT_WECHAT_WEBHOOK_URL` | `https://qyapi.weixin.qq.com/...` | 企业微信机器人 webhook |

部署后可在 `/api/health/sources` 中查看 `api_football.budget` 字段确认告警状态。

### 1.5 本地数据库准备

- [ ] 已执行 `alembic upgrade head`
- [ ] 数据库包含 48 队 / 104 场 / 48 积分榜：`sqlite3 data/worldcup2026.db "SELECT COUNT(*) FROM teams; SELECT COUNT(*) FROM matches; SELECT COUNT(*) FROM standings;"`
- [ ] 数据无 placeholder / group_name='Z' 等异常

---

## 二、Docker 构建验证

在有 Docker 的环境执行：

```bash
cd worldcup2026-platform
docker build -t wc2026:test .
docker run --rm -v ./data:/data -p 8000:8000 wc2026:test
```

另开终端检查：

```bash
curl http://localhost:8000/health
# 期望返回 200，version=0.15.0，scheduler_running=true
curl http://localhost:8000/api/teams | jq length  # 48
curl http://localhost:8000/api/matches | jq length # 104
```

---

## 三、Fly.io 部署

### 3.1 首次部署（数据库为空）

1. 临时修改 `fly.toml`：
   ```yaml
   env:
     SKIP_STARTUP_SYNC: "false"
   ```
2. 部署：
   ```bash
   flyctl deploy
   ```
3. 等待 2-3 分钟，确认 lifespan 完成首次同步：
   ```bash
   flyctl logs -a wc2026-fifa-platform
   ```
4. 验证数据：
   ```bash
   flyctl ssh console -a wc2026-fifa-platform -C 'sqlite3 /data/worldcup2026.db "SELECT COUNT(*) FROM teams; SELECT COUNT(*) FROM matches;"'
   ```

### 3.2 稳定后部署（已有数据库）

1. 恢复 `fly.toml`：
   ```yaml
   env:
     SKIP_STARTUP_SYNC: "true"
   ```
2. 若需带数据迁移：
   ```bash
   ./migrate_data_to_fly.sh
   ```
3. 部署：
   ```bash
   flyctl deploy
   ```

---

## 四、部署后验证

### 4.1 基础健康

```bash
APP=https://wc2026-fifa-platform.fly.dev

curl $APP/health | jq
curl $APP/api/health/sources | jq
```

期望：
- `/health` 返回 `200`，`version` 正确
- `scheduler_running=true`
- `freshness` 为 `fresh` 或 `recent`
- 若启用 API-Football：`/api/health/sources` 中 `api_football.budget.level` 为 `ok`，且阈值配置正确

### 4.2 数据完整性

```bash
curl $APP/api/teams | jq length        # 48
curl $APP/api/matches | jq length       # 104
curl $APP/api/groups | jq length        # 12
curl $APP/api/standings | jq length     # 48
curl $APP/api/bracket | jq '.round_of_32 | length'  # 16
```

### 4.3 安全基线

- [ ] `/api/docs` 返回 `404`（DEBUG=false）
- [ ] admin 端点（如 `/api/admin/sync/status`）无 `X-Admin-Token` 时返回 `403`
- [ ] CORS 预检只放行配置的域名

### 4.4 赔率数据

- [ ] 若配置了 `ODDS_API_KEY`，访问 `/#/odds` 页面，状态栏应显示 `the_odds_api` 且无「模拟数据」标签
- [ ] 若未配置 key，页面应显示「模拟数据」警告，且 6h 调度器不会生成新 mock 快照

### 4.5 前端资源

- [ ] 首页 `/` 正常加载
- [ ] Service Worker 注册成功（DevTools → Application → Service Workers → scope `/`）
- [ ] 直接访问 `/#/match/1` 或 `/#/odds` 不 404
- [ ] 移动端底部 Tab 不挤压

---

## 五、监控与回滚

### 5.1 监控

- [ ] Fly.io 仪表盘显示实例健康
- [ ] `/health` 未频繁返回 `503`
- [ ] 日志无大量 `多源启动同步失败` 或 `scheduler` 异常

### 5.2 回滚

若部署后异常：

```bash
# 回滚到上一版本
flyctl deploy --image wc2026-fifa-platform:previous

# 或本地回滚代码后重新部署
git checkout <previous-tag>
flyctl deploy
```

---

## 六、已知限制（上线后迭代）

| 项 | 说明 | 优先级 |
|---|---|---|
| 球员 360° 档案 | 未实现 | P1 |
| 伤停/转会情报 | 未接入数据源 | P1 |
| 专业/简洁模式 | 未实现 | P1 |
| 预测「五位一体」展示 | 仅胜平负概率 | P1 |
| 实时高阶可视化 | 无 xG 时间线/热图 | P1 |
| 多语言 | 仅中文 | P2 |
| `match_stats` 表 | 空表，赛后统计未自动同步 | P2 |
| `team_elo_ratings` 表 | 死表，仅历史保留 | P2 |
| 日志结构化 | 仍有部分 `print()` | P2 |
