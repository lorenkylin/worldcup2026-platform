# v0.12.0 — Production Dockerfile
# 基镜像: python 3.13 slim (Debian 12 bookworm) - 体积小 (~150MB) + 长期支持
FROM python:3.13-slim-bookworm AS base

# 系统依赖 — alembic/uvicorn 都需要
# build-essential: 部分 pip 包需要编译 (e.g. numpy 优化版)
# libffi-dev / libssl-dev: cryptography 等 SSL 库
# curl: HEALTHCHECK 用
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# 工作目录
WORKDIR /app

# 先复制 requirements 利用 Docker layer cache
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再复制应用代码 (代码变更不会让 pip 层失效)
COPY . .

# 数据目录 — 持久化卷挂载点
# 容器内: /app/data/worldcup2026.db
# 主机: 主机路径:/app/data
RUN mkdir -p /app/data /app/logs

# 非 root 用户运行 (安全最佳实践)
# 容器启动时先以 root 修正持久卷权限，再降权到 appuser
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# 入口脚本：处理 Fly.io /data 等持久卷的所有者后再降权运行
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 端口
EXPOSE 8000

# 健康检查 — Docker 自己也能用
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令 — 通过 entrypoint 降权到 appuser 后运行 uvicorn
CMD ["/app/entrypoint.sh", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
