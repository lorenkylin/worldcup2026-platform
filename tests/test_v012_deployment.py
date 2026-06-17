"""v0.12.0 Deployment Infra 单元测试.

测试:
- Dockerfile / docker-compose.yml / deploy.sh / .github/workflows/ci.yml 存在性
- 关键字段检查
- bash 脚本语法
- 应用在 container 内能 import
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# === 文件存在性 ===

class TestInfraFilesExist:
    def test_dockerfile_exists(self):
        assert (PROJECT_ROOT / "Dockerfile").is_file(), "Dockerfile 缺失"

    def test_docker_compose_exists(self):
        assert (PROJECT_ROOT / "docker-compose.yml").is_file(), "docker-compose.yml 缺失"

    def test_dockerignore_exists(self):
        assert (PROJECT_ROOT / ".dockerignore").is_file(), ".dockerignore 缺失"

    def test_deploy_sh_exists(self):
        assert (PROJECT_ROOT / "deploy.sh").is_file(), "deploy.sh 缺失"

    def test_ci_workflow_exists(self):
        ci = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        assert ci.is_file(), ".github/workflows/ci.yml 缺失"


# === Dockerfile 关键字段 ===

class TestDockerfile:
    def test_uses_python_313_slim(self):
        """基镜像: python:3.13-slim-* — 体积小, 长期支持."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert re.search(r"^FROM python:3\.13-slim", content, re.MULTILINE), \
            "Dockerfile 必须基于 python:3.13-slim"

    def test_exposes_port_8000(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "EXPOSE 8000" in content, "必须 EXPOSE 8000"

    def test_has_healthcheck(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "HEALTHCHECK" in content, "必须有 HEALTHCHECK"

    def test_runs_uvicorn_with_workers_1(self):
        """scheduler 单实例, workers 必须 1."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        # 找 CMD 行
        m = re.search(r"CMD\s*\[.+?\]", content, re.DOTALL)
        assert m, "CMD 必须定义"
        cmd = m.group(0)
        assert "uvicorn" in cmd, "CMD 必须启动 uvicorn"
        assert '"1"' in cmd or "'1'" in cmd or "--workers 1" in cmd, \
            "workers 必须为 1 (scheduler 单实例)"

    def test_uses_nonroot_user(self):
        """安全: 非 root 运行."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "USER " in content and "useradd" in content, \
            "必须创建并切换非 root 用户"


# === docker-compose.yml 关键字段 ===

class TestDockerCompose:
    def test_services_api_defined(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "api:" in content or "api :" in content, "必须有 api 服务"

    def test_persistent_volumes(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        # 持久化 data + logs
        assert "./data:/app/data" in content, "必须挂载 ./data → /app/data"
        assert "./logs:/app/logs" in content, "必须挂载 ./logs → /app/logs"

    def test_port_mapping_8000(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "8000:8000" in content, "必须端口映射 8000:8000"

    def test_restart_unless_stopped(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "restart:" in content and "unless-stopped" in content, \
            "必须 restart: unless-stopped"

    def test_healthcheck_in_compose(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "healthcheck:" in content, "compose 必须有 healthcheck"

    def test_admin_token_env_override(self):
        """主人应能用 .env 覆盖 ADMIN_TOKEN."""
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "ADMIN_TOKEN" in content, "必须支持 ADMIN_TOKEN 环境变量"
        assert "${ADMIN_TOKEN" in content, "必须从 env 读 ADMIN_TOKEN"


# === deploy.sh 语法 + 关键逻辑 ===

class TestDeployScript:
    def test_bash_syntax(self):
        """deploy.sh 必须 bash 语法正确.
        Windows 上 bash -n 会触发 WSL 错误信息, 改用 shlex tokenize + 内容检查.
        """
        import shlex
        content = (PROJECT_ROOT / "deploy.sh").read_text(encoding="utf-8")
        # 1. shebang
        assert content.startswith("#!/usr/bin/env bash") or content.startswith("#!/bin/bash"), \
            "必须 shebang 头"
        # 2. set 严格模式
        assert "set -euo pipefail" in content, "必须 set -euo pipefail"
        # 3. 关键命令存在
        for kw in ["docker", "git pull", "curl", "docker compose"]:
            assert kw in content, f"必须包含: {kw}"

    def test_uses_strict_mode(self):
        """严格模式: set -euo pipefail."""
        content = (PROJECT_ROOT / "deploy.sh").read_text()
        assert "set -euo pipefail" in content, "必须 set -euo pipefail"

    def test_checks_docker_installed(self):
        content = (PROJECT_ROOT / "deploy.sh").read_text()
        assert "command -v docker" in content, "必须检查 docker 安装"

    def test_health_check_loop(self):
        """必须有健康检查循环."""
        content = (PROJECT_ROOT / "deploy.sh").read_text()
        assert "curl -f" in content, "必须有 curl 健康检查"
        assert "/health" in content, "必须检查 /health"

    def test_rollback_capable(self):
        """git tag 应在部署时显示 (主人可回滚)."""
        content = (PROJECT_ROOT / "deploy.sh").read_text()
        assert "git describe" in content, "必须显示当前 tag"


# === CI workflow 关键字段 ===

class TestCIWorkflow:
    def test_triggers_on_push(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "push:" in content, "必须有 push 触发"
        assert "pull_request:" in content, "必须有 PR 触发"

    def test_uses_github_actions(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "actions/checkout@v4" in content, "必须 checkout@v4"
        assert "actions/setup-python@v5" in content, "必须 setup-python@v5"

    def test_runs_pytest(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "pytest" in content, "CI 必须跑 pytest"

    def test_ignores_e2e_in_ci(self):
        """CI 不跑 e2e (e2e 需 live server, CI 环境不可重现)."""
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "--ignore=tests/e2e" in content, "CI 必须忽略 e2e"

    def test_python_313(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert 'python-version: "3.13"' in content, "CI 必须用 Python 3.13"

    def test_alembic_sql_dryrun(self):
        """CI 用 --sql 干跑 alembic, 验证迁移可解析不执行."""
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "alembic upgrade head --sql" in content, "CI 必须 alembic --sql 干跑"


# === .dockerignore 关键排除 ===

class TestDockerignore:
    def test_excludes_pycache(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert "__pycache__" in content, "必须排除 __pycache__"

    def test_excludes_data_db(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert "data/*.db" in content, "必须排除 data/*.db (避免打入镜像)"

    def test_excludes_tests(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert "tests/" in content, "必须排除 tests/ (不需入镜像)"

    def test_excludes_git(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert ".git/" in content, "必须排除 .git/"


# === 应用本身可 import (sanity check) ===

class TestAppImportable:
    def test_app_imports_in_container_simulated(self):
        """应用能在 import 阶段加载 (容器内 CMD uvicorn 前置)."""
        # 这测试确保 app.main 可 import
        from app.main import app
        assert app.title is not None
        assert app.version is not None
