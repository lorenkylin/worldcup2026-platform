#!/bin/bash
set -e

# Fly.io 挂载 /data 为 root:root 755，非 root 用户无法写入。
# 容器以 root 启动，先修正持久卷所有者，再降权到 appuser 运行主进程。
for dir in /data /app/data /app/logs; do
  if [ -d "$dir" ]; then
    chown -R appuser:appuser "$dir"
  fi
done

exec gosu appuser "$@"
