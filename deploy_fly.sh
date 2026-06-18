#!/bin/bash
# v0.14.0 — Fly.io 一键部署脚本
# 主人执行, 奴才不能持有主人 token
#
# 用法:
#   export FLY_API_TOKEN=<你的-fly-token>
#   ./deploy_fly.sh

set -euo pipefail

APP_NAME="wc2026-fifa-platform"
REGION="hkg"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_color() { echo -e "${2}${1}${NC}"; }

# 1. 前置检查
echo_color "🔍 步骤 1/6: 前置检查" "$BLUE"
echo ""

if [ -z "${FLY_API_TOKEN:-}" ]; then
  echo_color "❌ FLY_API_TOKEN 未设置" "$RED"
  echo ""
  echo "主人请按以下步骤获取 token:"
  echo "  1. 访问 https://fly.io/orgs/<你的-个人-org>/settings/tokens"
  echo "     (主人需要先注册 fly.io 账号 + 绑卡, 奴才不能注册)"
  echo "  2. 点击 'Create Token' (推荐 Read/Write 权限)"
  echo "  3. 复制生成的 FLY_API_TOKEN"
  echo "  4. 终端执行: export FLY_API_TOKEN=<你的-token>"
  echo "  5. 重新跑: ./deploy_fly.sh"
  echo ""
  exit 1
fi
echo "✅ FLY_API_TOKEN 已设置 (${#FLY_API_TOKEN} 字符)"

if ! command -v flyctl &> /dev/null; then
  echo_color "❌ flyctl 未安装" "$RED"
  echo ""
  echo "主人请按系统安装:"
  echo "  Windows (PowerShell): iwr https://fly.io/install.ps1 -useb | iex"
  echo "  macOS:                brew install flyctl"
  echo "  Linux:                curl -L https://fly.io/install.sh | sh"
  echo ""
  exit 1
fi
echo "✅ flyctl 已安装 ($(flyctl version))"

# 2. 显示当前状态
echo ""
echo_color "📊 步骤 2/6: 当前部署状态" "$BLUE"
echo ""

COMMIT=$(git rev-parse --short HEAD)
VERSION=$(grep '^    version=' app/main.py | head -1 | cut -d'"' -f2)

echo "  📌 commit:  $COMMIT"
echo "  📌 version: $VERSION"
echo "  📌 region:  $REGION (香港)"
echo "  📌 app:     $APP_NAME"

if flyctl apps show "$APP_NAME" &> /dev/null; then
  EXISTING_VERSION=$(flyctl status -a "$APP_NAME" 2>/dev/null | grep -oP 'Image: \K[^ ]+' | head -1 || echo "unknown")
  echo "  📌 现有:    $APP_NAME 已存在"
else
  echo "  📌 现有:    无 (首次部署)"
fi

# 3. 认证
echo ""
echo_color "🔐 步骤 3/6: Fly 认证" "$BLUE"
echo ""

export FLY_API_TOKEN
echo "✅ 已用 FLY_API_TOKEN 认证"

# 4. 创建 app (如不存在)
echo ""
echo_color "📦 步骤 4/6: 创建 app + 持久卷 (如不存在)" "$BLUE"
echo ""

if ! flyctl apps show "$APP_NAME" &> /dev/null; then
  echo "  创建 app: $APP_NAME"
  flyctl apps create "$APP_NAME" --org personal
  echo "  ✅ app 创建成功"
else
  echo "  ⏭️  app 已存在, 跳过"
fi

if ! flyctl volumes show wc2026_data -a "$APP_NAME" &> /dev/null 2>&1; then
  echo "  创建持久卷: wc2026_data (1GB, $REGION)"
  flyctl volumes create wc2026_data --size 1 --region "$REGION" -a "$APP_NAME"
  echo "  ✅ 持久卷创建成功"
else
  echo "  ⏭️  持久卷 wc2026_data 已存在, 跳过"
fi

# 5. 部署
echo ""
echo_color "🚀 步骤 5/6: 部署" "$BLUE"
echo ""
echo "  flyctl deploy --remote-only (Fly 自动构建 + 部署)"
echo ""

flyctl deploy --remote-only -a "$APP_NAME"

# 6. 健康检查
echo ""
echo_color "⏳ 步骤 6/6: 健康检查 (60s 超时)" "$BLUE"
echo ""

HEALTH_URL="https://$APP_NAME.fly.dev/health"
for i in $(seq 1 12); do
  sleep 5
  if curl -s -f "$HEALTH_URL" > /dev/null 2>&1; then
    echo ""
    echo_color "✅ 部署成功!" "$GREEN"
    echo ""
    echo "  🌐 公网 URL: https://$APP_NAME.fly.dev"
    echo "  📊 Cockpit:   https://$APP_NAME.fly.dev/#/cockpit"
    echo "  🏥 Health:    $HEALTH_URL"
    echo "  📡 Sync:      https://$APP_NAME.fly.dev/api/health/sync-status"
    echo ""
    echo_color "📋 部署后主人必做 3 件事:" "$YELLOW"
    echo "  1. ./fly_secrets_set.sh  (注入 ADMIN_TOKEN)"
    echo "  2. ./migrate_data_to_fly.sh  (双跑带数据 Q2=B)"
    echo "  3. 浏览器打开 Cockpit URL 验证 5 卡片渲染"
    echo ""
    flyctl status -a "$APP_NAME" 2>/dev/null | head -20 || true
    exit 0
  fi
  echo "  ... attempt $i/12 ($((i*5))s)"
done

echo ""
echo_color "❌ 60s 健康检查超时" "$RED"
echo ""
echo "主人请按以下命令诊断:"
echo "  flyctl logs -a $APP_NAME"
echo "  flyctl status -a $APP_NAME"
echo "  flyctl ssh console -a $APP_NAME -C 'ls -la /data'"
exit 1
