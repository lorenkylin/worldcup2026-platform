"""Windows 下可靠启动 uvicorn（指定 cwd + CREATE_NEW_PROCESS_GROUP）."""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

subprocess.Popen(
    [
        sys.executable,
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
    ],
    cwd=PROJECT_DIR,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)

print(f"[start_server] uvicorn started in {PROJECT_DIR}")
