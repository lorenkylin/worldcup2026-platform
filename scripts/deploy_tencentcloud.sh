#!/bin/bash
# 腾讯云 Lighthouse/CVM 自助部署脚本
# 用法：
#   1. 购买 Ubuntu 22.04 服务器，开放 22/80/443 端口
#   2. 配置域名 A 记录指向服务器 IP
#   3. 上传项目到 /opt/wc2026（git clone 或 scp）
#   4. 修改下方 DOMAIN 变量
#   5. 执行：sudo bash scripts/deploy_tencentcloud.sh

set -e

# ============ 用户配置区 ============
DOMAIN="wc2026.example.com"          # 替换为你的域名
ADMIN_TOKEN="change-me-to-strong-token" # 替换为强密码
APP_DIR="/opt/wc2026"
PYTHON_BIN="/usr/bin/python3"
# ===================================

# 颜色输出
red() { echo -e "\033[31m$*\033[0m"; }
green() { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }

if [ "$EUID" -ne 0 ]; then
  red "请使用 sudo 运行本脚本"
  exit 1
fi

yellow "[1/8] 更新系统..."
apt-get update && apt-get upgrade -y

yellow "[2/8] 安装依赖..."
apt-get install -y python3 python3-venv python3-pip nginx git certbot python3-certbot-nginx

yellow "[3/8] 准备应用目录..."
mkdir -p "$APP_DIR"
# 如果当前目录不是 APP_DIR，提示用户
if [ ! -f "$APP_DIR/app/main.py" ]; then
  yellow "请将项目代码放到 $APP_DIR，或在此脚本所在项目根目录运行"
  # 兼容：脚本在项目根目录执行
  if [ -f "app/main.py" ]; then
    APP_DIR="$(pwd)"
    green "检测到项目根目录：$APP_DIR"
  else
    red "未找到 app/main.py，请确认路径"
    exit 1
  fi
fi

cd "$APP_DIR"

yellow "[4/8] 创建 Python 虚拟环境并安装依赖..."
if [ ! -d "$APP_DIR/venv" ]; then
  $PYTHON_BIN -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

yellow "[5/8] 初始化数据库..."
if [ ! -f "$APP_DIR/data/worldcup2026.db" ]; then
  python data/seed.py
fi

yellow "[6/8] 配置 Systemd 服务..."
cat > /etc/systemd/system/wc2026.service <<EOF
[Unit]
Description=2026 FIFA World Cup Analysis Platform
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="PYTHONPATH=$APP_DIR"
Environment="ADMIN_TOKEN=$ADMIN_TOKEN"
ExecStart=$APP_DIR/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wc2026
systemctl restart wc2026

yellow "[7/8] 配置 Nginx..."
cat > /etc/nginx/sites-available/wc2026 <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        root $APP_DIR/app/static;
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

if [ -f /etc/nginx/sites-enabled/default ]; then
  rm /etc/nginx/sites-enabled/default
fi
ln -sf /etc/nginx/sites-available/wc2026 /etc/nginx/sites-enabled/wc2026
nginx -t
systemctl restart nginx

yellow "[8/8] 申请 SSL 证书..."
if [ "$DOMAIN" != "wc2026.example.com" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN"
else
  red "请先将脚本中的 DOMAIN 替换为你的真实域名，再重新运行申请 SSL"
fi

green "=========================================="
green "部署完成！"
green "访问地址：http://$DOMAIN 或 https://$DOMAIN"
green "健康检查：http://$DOMAIN/health"
green "管理接口需携带 Header: X-Admin-Token: $ADMIN_TOKEN"
green "=========================================="
