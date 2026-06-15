# 生产环境 Dockerfile
# 用法：docker build -f scripts/Dockerfile -t wc2026:latest .

FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖，利用缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY data/ ./data/
COPY scripts/ ./scripts/

# 创建数据目录（用于挂载卷）
RUN mkdir -p /app/data

# 默认暴露 8000
EXPOSE 8000

# 启动 uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
