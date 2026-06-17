#!/bin/bash
# v0.13.0 — Fly secrets 注入脚本
# 主人 ADMIN_TOKEN + 可选 FOOTBALL_DATA_API_KEY 注入 Fly secrets
# 关键: token 不入代码, 不入 git, 只在 Fly 控制台加密存储

set -euo pipefail

APP_NAME="wc2026-fifa-platform"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_color() { echo -e "${2}${1}${NC}"; }

if ! command -v flyctl &> /dev/null; then
  echo "❌ flyctl 未安装"
  exit 1
fi

if [ -z "${FLY_API_TOKEN:-}" ]; then
  echo "❌ FLY_API_TOKEN 未设置"
  echo "主人请: export FLY_API_TOKEN=<你的-token>"
  exit 1
fi

export FLY_API_TOKEN

echo_color "🔐 注入 secrets 到 $APP_NAME" "$YELLOW"
echo ""
echo "  ADMIN_TOKEN (必填, 主人自定 16+ 字符)"
echo "  FOOTBALL_DATA_API_KEY (可选, 留空跳过)"
echo ""

# 1. ADMIN_TOKEN
while true; do
  read -s -p "  请输入 ADMIN_TOKEN (输入不显示): " ADMIN_TOKEN
  echo ""
  if [ -z "$ADMIN_TOKEN" ]; then
    echo "  ❌ 主人取消 (空 token), 退出"
    exit 1
  fi
  if [ ${#ADMIN_TOKEN} -lt 16 ]; then
    echo "  ❌ 太短 (主人至少 16 字符), 重输"
    continue
  fi
  read -s -p "  再输一次确认: " ADMIN_TOKEN_CONFIRM
  echo ""
  if [ "$ADMIN_TOKEN" != "$ADMIN_TOKEN_CONFIRM" ]; then
    echo "  ❌ 两次不一致, 重输"
    continue
  fi
  break
done

echo "  设置 ADMIN_TOKEN ..."
flyctl secrets set "ADMIN_TOKEN=$ADMIN_TOKEN" -a "$APP_NAME" > /dev/null
echo "  ✅ ADMIN_TOKEN 已设置"

# 2. FOOTBALL_DATA_API_KEY (可选)
echo ""
read -p "  请输入 FOOTBALL_DATA_API_KEY (留空跳过): " FB_KEY
if [ -n "$FB_KEY" ]; then
  echo "  设置 FOOTBALL_DATA_API_KEY ..."
  flyctl secrets set "FOOTBALL_DATA_API_KEY=$FB_KEY" -a "$APP_NAME" > /dev/null
  echo "  ✅ FOOTBALL_DATA_API_KEY 已设置"
else
  echo "  ⏭️  跳过 FOOTBALL_DATA_API_KEY (赔率模块用 mock)"
fi

# 3. WC26_BASE_URL (可选, 默认世界官)
echo ""
read -p "  请输入 WC26_BASE_URL (留空用默认 https://www.worldcup26.ir): " WC26_URL
WC26_URL=${WC26_URL:-https://www.worldcup26.ir}
flyctl secrets set "WC26_BASE_URL=$WC26_URL" -a "$APP_NAME" > /dev/null
echo "  ✅ WC26_BASE_URL=$WC26_URL"

echo ""
echo_color "✅ 全部 secrets 设置完成" "$GREEN"
echo ""
echo "主人可执行 'flyctl secrets list -a $APP_NAME' 验证"
echo ""
echo "⚠️  重要: secrets 不会显示完整值 (Fly 安全设计)"
echo "    只显示 KEY 列表"
