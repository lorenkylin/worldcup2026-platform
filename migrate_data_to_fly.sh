#!/bin/bash
# v0.13.0 — 数据迁移脚本 (Q2=B 带数据)
# 主人执行: 把本地 SQLite + sync_status.json 上传到 Fly 持久卷
#
# 双跑期间:
#   - 本地 (127.0.0.1:8000) 继续跑
#   - Fly (wc2026-fifa-platform.fly.dev) 独立跑
#   - 两条真理源, 主人选一个作为"权威"

set -euo pipefail

APP_NAME="wc2026-fifa-platform"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TAR_FILE="/tmp/wc2026_data_${TIMESTAMP}.tar.gz"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_color() { echo -e "${2}${1}${NC}"; }

if ! command -v flyctl &> /dev/null; then
  echo "❌ flyctl 未安装"
  exit 1
fi

if [ -z "${FLY_API_TOKEN:-}" ]; then
  echo "❌ FLY_API_TOKEN 未设置"
  exit 1
fi

export FLY_API_TOKEN

# 1. 本地打包
echo_color "📦 步骤 1/4: 打包本地 data/" "$BLUE"
echo ""

cd "$(dirname "$0")"

if [ ! -f data/worldcup2026.db ]; then
  echo "❌ data/worldcup2026.db 不存在"
  echo "主人请先跑:  启动 uvicorn (lifespan 会自动 sync 一次)"
  exit 1
fi

DB_SIZE=$(stat -c %s data/worldcup2026.db 2>/dev/null || stat -f %z data/worldcup2026.db)
echo "  📊 SQLite 大小: $(numfmt --to=iec $DB_SIZE 2>/dev/null || echo ${DB_SIZE} bytes)"

tar -czf "$TAR_FILE" data/worldcup2026.db data/sync_status.json 2>/dev/null || \
  tar -czf "$TAR_FILE" data/worldcup2026.db

TAR_SIZE=$(stat -c %s "$TAR_FILE" 2>/dev/null || stat -f %z "$TAR_FILE")
echo "  ✅ 打包完成: $TAR_FILE ($(numfmt --to=iec $TAR_SIZE 2>/dev/null || echo ${TAR_SIZE} bytes))"
echo ""

# 2. 主人手动上传 (奴才不能持有 SFTP 凭证)
echo_color "📤 步骤 2/4: 主人手动上传到 Fly SFTP" "$YELLOW"
echo ""
echo "  在主人本地新开一个 shell 跑:"
echo ""
echo "    flyctl sftp shell -a $APP_NAME"
echo "    > put $TAR_FILE /tmp/wc2026_data.tar.gz"
echo "    > exit"
echo ""
echo "  ⚠️  奴才不能持有主人的 flyctl auth 凭证, 只能写到 runbook"
echo ""

read -p "  主人上传完成了吗? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ 主人取消"
  exit 1
fi

# 3. 在 Fly 容器内解包
echo ""
echo_color "📂 步骤 3/4: 在 Fly 容器内解包到 /data/" "$BLUE"
echo ""

flyctl ssh console -a "$APP_NAME" -C "ls -la /tmp/wc2026_data.tar.gz && tar -xzf /tmp/wc2026_data.tar.gz -C / && rm -rf /tmp/wc2026_data.tar.gz && ls -la /data/ && du -sh /data/"

# 4. 重启 app + 健康检查
echo ""
echo_color "🔄 步骤 4/4: 重启 app 让 scheduler 重新连接" "$BLUE"
echo ""

flyctl apps restart "$APP_NAME"

echo ""
echo "  等待 60s 让 app 启动 + scheduler 初始化 ..."
sleep 60

echo ""
echo_color "✅ 验证上传" "$GREEN"
echo ""
echo "  flyctl ssh console -a $APP_NAME -C 'sqlite3 /data/worldcup2026.db \"SELECT COUNT(*) FROM teams;\"'"
echo ""
echo "  或浏览器: https://$APP_NAME.fly.dev/api/teams?limit=1"
echo ""
echo "  主人期待看到 96 队 (master_teams 表)"
echo "  飞 → 200 + 96 = 上传成功"
echo "  飞 → 404/500 = 检查 flyctl logs"
