#!/bin/bash
# Docker Compose 自助部署脚本
# 前置条件：服务器已安装 Docker + Docker Compose
# 用法：
#   1. 上传项目到服务器（如 /opt/wc2026）
#   2. cd /opt/wc2026
#   3. sudo bash scripts/deploy_docker.sh

set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo "[1/3] 构建镜像..."
docker compose -f scripts/docker-compose.yml build

echo "[2/3] 初始化数据卷（首次运行）..."
# 确保数据目录存在
mkdir -p data

if [ ! -f "data/worldcup2026.db" ]; then
  echo "首次运行，初始化数据库..."
  docker compose -f scripts/docker-compose.yml run --rm wc2026 python data/seed.py
fi

echo "[3/3] 启动服务..."
docker compose -f scripts/docker-compose.yml up -d

echo "=========================================="
echo "Docker 部署完成！"
echo "本地访问：http://127.0.0.1:8000"
echo "如需对外访问，请在前方配置 Nginx 或 Cloudflare Tunnel"
echo "=========================================="
