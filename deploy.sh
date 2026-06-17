#!/usr/bin/env bash
# v0.12.0 — VPS 部署脚本
# 用途: 主人 SSH 到 VPS 后跑这个脚本, 一键部署最新代码
#
# 前置条件 (主人负责):
# 1. 一台 Linux VPS (Ubuntu 22.04+ / Debian 12+)
# 2. VPS 上安装: docker + docker-compose
# 3. 主机 data/ + logs/ 目录存在 (脚本会建)
# 4. .env 文件在主机 (含 ADMIN_TOKEN + FOOTBALL_DATA_API_KEY)
#
# 用法:
#   chmod +x deploy.sh
#   ./deploy.sh                      # 拉最新代码 + 重新部署
#   ./deploy.sh --no-pull            # 不 git pull, 只重新部署 (调试用)
#   ./deploy.sh --logs               # 部署后看日志
#
# 失败回滚: 镜像 tag 用 v0.X.Y, 可手动 docker-compose down + 切回旧 tag

set -euo pipefail  # 严格模式: 错就退, undefined 变量错就退, pipe 错也退

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 解析参数
PULL=true
LOGS=false
for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=false ;;
    --logs) LOGS=true ;;
    --help|-h)
      echo "用法: $0 [--no-pull] [--logs]"
      exit 0
      ;;
    *) err "未知参数: $arg"; exit 1 ;;
  esac
done

# 0. 前置检查
log "0. 前置检查"

if ! command -v docker &> /dev/null; then
  err "docker 未安装. 主人先装: https://docs.docker.com/engine/install/"
  exit 1
fi
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
  err "docker-compose 未安装. 主人先装: https://docs.docker.com/compose/install/"
  exit 1
fi

if [ ! -f .env ]; then
  warn ".env 不存在, 用环境变量默认值 (不安全)"
  warn "建议建 .env 含 ADMIN_TOKEN + FOOTBALL_DATA_API_KEY"
fi

mkdir -p data logs

# 1. 拉代码
if [ "$PULL" = true ]; then
  log "1. git pull origin master"
  git pull origin master || { err "git pull 失败"; exit 1; }
else
  warn "1. 跳过 git pull (--no-pull)"
fi

# 2. 显示当前版本
log "2. 当前 commit + tag"
COMMIT=$(git rev-parse --short HEAD)
TAG=$(git describe --tags --exact-match 2>/dev/null || echo "no-tag")
log "   commit: $COMMIT"
log "   tag: $TAG"

# 3. 停旧容器
log "3. 停旧容器"
docker compose down --remove-orphans || warn "没有旧容器"

# 4. 重新 build
log "4. 重新 build 镜像 (无 cache)"
docker compose build --no-cache || { err "build 失败"; exit 1; }

# 5. 启动
log "5. 启动新容器"
docker compose up -d || { err "启动失败"; exit 1; }

# 6. 等 health
log "6. 等健康检查通过 (最多 60s)"
for i in $(seq 1 30); do
  if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    log "   ✅ 健康检查通过 (第 $((i*2)) 秒)"
    break
  fi
  if [ $i -eq 30 ]; then
    err "   ❌ 健康检查 60s 内未通过"
    err "   看日志: docker compose logs --tail=50 api"
    exit 1
  fi
  sleep 2
done

# 7. 验证
log "7. 验证部署"
HEALTH=$(curl -s http://localhost:8000/health)
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

# 8. 打印容器状态
log "8. 容器状态"
docker compose ps

log "🎉 部署完成. 访问: http://<vps-ip>:8000"
log "   日志: docker compose logs -f api"
log "   停止: docker compose down"

# 9. --logs 模式
if [ "$LOGS" = true ]; then
  log "9. 跟踪日志 (Ctrl+C 退出)"
  docker compose logs -f api
fi
