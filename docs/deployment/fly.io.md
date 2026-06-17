# Fly.io 部署指南 — 5 分钟上线

> v0.13.0 — 主人执行, 奴才不持有主人任何凭证

## 1. 为什么选 Fly.io

| 维度 | Fly.io | 腾讯云轻量 | AWS Lightsail |
|---|---|---|---|
| 免费 tier | 256MB × 3 实例 + 1GB 卷 | ❌ | ❌ |
| 区域 | hkg 香港 | 国内 | 国外 |
| 部署 | 1 行 `flyctl deploy` | 复杂 | 中 |
| 域名 | `xxx.fly.dev` 免费 | 需自己买 | 需自己买 |
| **主人 0 元/月** | ✅ | ❌ | ❌ |

**结论**: 17 天世界杯验证窗口, Fly.io 免费 tier 0 元最划算。

## 2. 主人 4 步上线 (约 11 分钟)

### 步骤 1: 注册 Fly.io 账号 (3 min)
1. 访问 https://fly.io/
2. 主人用邮箱注册 (主人操作, 奴才不持有)
3. **必须绑卡** 验证身份 (免费 tier 也不免, 主人操作)

### 步骤 2: 安装 flyctl (1 min)
```powershell
# Windows PowerShell
iwr https://fly.io/install.ps1 -useb | iex
```
```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh
```

### 步骤 3: 生成 API Token (30s)
1. 主人浏览器访问: https://fly.io/orgs/personal/settings/tokens
2. 点 `Create Token` (Read/Write 权限)
3. 复制 token
4. 在主人本地 shell 跑:
   ```bash
   export FLY_API_TOKEN=<主人粘贴的 token>
   ```
   ⚠️  这个 token 不入 git, 主人保管好

### 步骤 4: 部署 (5 min)
```bash
cd worldcup2026-platform

# 1. 一键部署 (Dockerfile 已复用 v0.12)
./deploy_fly.sh

# 2. 注入 secrets (ADMIN_TOKEN 必填)
./fly_secrets_set.sh

# 3. Q2=B 带数据: 上传本地 SQLite
./migrate_data_to_fly.sh
#   注: 第 2 步需主人手动开新 shell 跑 flyctl sftp shell, 见脚本提示

# 4. 验证
curl https://wc2026-fifa-platform.fly.dev/health
# 期待: {"status":"healthy","version":"0.13.0",...}
```

## 3. 主人 17 天能访问的 URL

| URL | 内容 |
|---|---|
| https://wc2026-fifa-platform.fly.dev/ | H5 SPA 主页 |
| https://wc2026-fifa-platform.fly.dev/#/cockpit | 实时 Cockpit (5 卡片) |
| https://wc2026-fifa-platform.fly.dev/#/matches | 全部 105 场比赛 |
| https://wc2026-fifa-platform.fly.dev/#/bracket | 12 组 + R32 对阵 |
| https://wc2026-fifa-platform.fly.dev/#/simulator | Monte Carlo 10000 sims |
| https://wc2026-fifa-platform.fly.dev/#/odds | 价值投注 |
| https://wc2026-fifa-platform.fly.dev/health | 平台健康 (JSON) |
| https://wc2026-fifa-platform.fly.dev/api/health/sync-status | 数据新鲜度 |
| https://wc2026-fifa-platform.fly.dev/api/elo/live-accuracy | 真 forward 准确率 |
| https://wc2026-fifa-platform.fly.dev/api/teams?limit=1 | 96 队 API |

## 4. Q3=B 双跑架构 (主人已选)

```
┌─────────────────┐     ┌─────────────────┐
│  本地 (主人)     │     │  Fly.io (云)    │
│  127.0.0.1:8000 │     │  wc2026-...dev  │
│                 │     │                 │
│  lifespan       │     │  lifespan       │
│  scheduler 15min│     │  scheduler 15min│
│       ↓         │     │       ↓         │
│  /api/admin/    │     │  /api/admin/    │
│  sync_worldcup  │     │  sync_worldcup  │
│       ↓         │     │       ↓         │
│  data/worldcup  │     │  /data/worldcup │
│  2026.db        │     │  2026.db        │
│                 │     │                 │
│  真理源: 主人选  │     │  真理源: 主人选 │
└─────────────────┘     └─────────────────┘
         ↑                       ↑
         └─────── 主人浏览器 ────┘
                (任选 URL)
```

**双跑风险**:
- ⚠️ 两条真理源, 主人选一个作为"权威"
- ⚠️ worldcup26.ir 同步 15min, 两边会**慢 0-15min 漂移**
- ⚠️ 但 17 天窗口期, 漂移 < 1 小时, 不影响预测质量
- ✅ 本地 (127.0.0.1:8000) 仍跑: 主人开发/调试用
- ✅ Fly 跑: 主人朋友/手机上随时查

**主人选哪个做权威**:
- **本地**: 数据"刚刚才同步", 但只有主人能访问
- **Fly**: 公开 URL, 朋友能看, 但数据可能有 0-15min 滞后

**建议**: Fly 为主 (公开), 本地为辅 (调试), 漂移忽略不计

## 5. 主人常用命令 (cheat sheet)

```bash
# 查看 app 状态
flyctl status -a wc2026-fifa-platform

# 看实时日志 (最重要)
flyctl logs -a wc2026-fifa-platform

# 远程进容器
flyctl ssh console -a wc2026-fifa-platform

# 重启 app (migrate_data 后必做)
flyctl apps restart wc2026-fifa-platform

# 部署新版本
./deploy_fly.sh

# 更新 secrets
./fly_secrets_set.sh

# 删 app (终极清理)
flyctl apps destroy wc2026-fifa-platform
```

## 6. 主人故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| /health 返回 502 | 容器还在启动 | 等 40s 后重试 |
| 部署后 SQLite 空 | 没跑 migrate_data | `./migrate_data_to_fly.sh` |
| scheduler 不动 | worldcup26.ir 挂了 | 看 flyctl logs + `/api/health/sync-status` |
| 内存 OOM 杀进程 | 256MB 不够 | 升级到 shared-cpu-1x 512MB ($) |
| 公开 URL 被刷流量 | 公开有 DDoS 风险 | 主人可加 basic auth (v0.14 候选) |

## 7. 17 天后收尾

```bash
# 主人可保留免费 app (0 元挂着当备份)
# 或彻底删除:
flyctl apps destroy wc2026-fifa-platform
flyctl volumes delete wc2026_data -a wc2026-fifa-platform
```

## 8. 奴才不持有 (诚实点)

奴才**没有也不能创建**:
- ❌ Fly 账号 (主人注册)
- ❌ 绑卡 (主人操作)
- ❌ FLY_API_TOKEN (主人生成, 不入代码)
- ❌ ADMIN_TOKEN (主人自定, 不入代码)
- ❌ 域名 (主人可选绑, 需注册商账号)

奴才**只**写代码 + 写 runbook, 主人执行一键部署。
