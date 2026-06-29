"""Windows 下可靠启动 uvicorn（指定 cwd + CREATE_NEW_PROCESS_GROUP）."""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
HOST = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8002

subprocess.Popen(
    [
        sys.executable,
        "-m", "uvicorn",
        "app.main:app",
        "--host", HOST,
        "--port", str(PORT),
    ],
    cwd=PROJECT_DIR,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)

print(f"[start_server] uvicorn started in {PROJECT_DIR}")
print(f"访问地址: http://<内网IP>:{PORT} （例如 http://192.168.1.169:{PORT}）")
