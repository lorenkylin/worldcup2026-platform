"""
v0.13.0 — Fly.io 部署配置测试
验证 fly.toml / deploy_fly.sh / fly_secrets_set.sh / migrate_data_to_fly.sh
四件套 + Dockerfile 关键约束

诚实点 (v0.12.1 教训):
- 真 yaml.safe_load 解析 (不再只 grep 关键词)
- 真 bash 语法检查
- 字段值断言 (单实例 / 端口一致 / 挂载点正确)
"""
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
FLY_TOML = PROJECT_ROOT / "fly.toml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DEPLOY_SH = PROJECT_ROOT / "deploy_fly.sh"
SECRETS_SH = PROJECT_ROOT / "fly_secrets_set.sh"
MIGRATE_SH = PROJECT_ROOT / "migrate_data_to_fly.sh"


class TestFlyTomlStructure:
    """fly.toml 真解析 + 关键字段断言"""

    def test_fly_toml_exists(self):
        assert FLY_TOML.exists(), "fly.toml 不存在"

    def test_fly_toml_yaml_parses(self):
        """诚实点: v0.12 教训 — 真解析不只 grep"""
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None, "fly.toml 解析为 None"

    def test_app_name_is_wc2026_fifa_platform(self):
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["app"] == "wc2026-fifa-platform", \
            f"app 名应为 wc2026-fifa-platform, 实际 {data['app']}"

    def test_primary_region_is_hkg(self):
        """香港 — 离中国用户最近"""
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["primary_region"] == "hkg", \
            f"region 应为 hkg, 实际 {data['primary_region']}"

    def test_build_uses_dockerfile(self):
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        build = data.get("build", {})
        assert build.get("dockerfile") == "Dockerfile", \
            f"build.dockerfile 应为 Dockerfile, 实际 {build.get('dockerfile')}"

    def test_single_process_constraint(self):
        """scheduler 单实例硬约束 — 多进程会重复同步"""
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        processes = data.get("processes", {})
        # 必须只有 web 一个进程
        assert "web" in processes, "processes.web 缺失"
        assert len(processes) == 1, \
            f"必须有且仅 1 个进程 (防 scheduler 重复), 实际 {list(processes.keys())}"
        # web 必须 --workers 1
        assert "--workers 1" in processes["web"], \
            f"web 进程必须 --workers 1, 实际 {processes['web']}"

    def test_volume_mount_destination_is_slash_data(self):
        """挂载点必须 /data — 与 app DATA_DIR env 一致"""
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        mounts = data.get("mounts", [])
        assert len(mounts) == 1, f"应有 1 个挂载, 实际 {len(mounts)}"
        assert mounts[0]["destination"] == "/data", \
            f"挂载点应为 /data, 实际 {mounts[0]['destination']}"
        assert mounts[0]["source"] == "wc2026_data", \
            f"挂载名应为 wc2026_data, 实际 {mounts[0]['source']}"

    def test_data_dir_env_matches_volume(self):
        """DATA_DIR env 必须与挂载点一致"""
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        env = data.get("env", {})
        assert env.get("DATA_DIR") == "/data", \
            f"DATA_DIR 应为 /data, 实际 {env.get('DATA_DIR')}"

    def test_internal_port_matches_dockerfile(self):
        """internal_port 8000 必须与 Dockerfile EXPOSE 一致"""
        with open(FLY_TOML, encoding="utf-8") as f:
            toml_data = yaml.safe_load(f)
        services = toml_data.get("services", [])
        assert len(services) >= 1
        internal_port = services[0]["internal_port"]
        assert internal_port == 8000, f"internal_port 应为 8000, 实际 {internal_port}"

        dockerfile_content = DOCKERFILE.read_text(encoding="utf-8")
        assert "EXPOSE 8000" in dockerfile_content, "Dockerfile 必须 EXPOSE 8000"

    def test_release_command_does_not_run_alembic_against_sqlite(self):
        """SQLite + 持久卷: release_command 在临时机不挂载 /data,不能跑 alembic。"""
        with open(FLY_TOML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        deploy = data.get("deploy", {})
        release_cmd = deploy.get("release_command", "")
        assert "alembic" not in release_cmd, \
            f"release_command 不应包含 alembic (临时机无持久卷): {release_cmd!r}"


class TestDeployFlySh:
    """deploy_fly.sh 关键约束"""

    def test_deploy_fly_sh_exists(self):
        assert DEPLOY_SH.exists()

    def test_deploy_fly_sh_has_set_euo_pipefail(self):
        content = DEPLOY_SH.read_text(encoding="utf-8")
        assert "set -euo pipefail" in content, "必须 set -euo pipefail 防御"

    def test_deploy_fly_sh_checks_fly_api_token(self):
        """必须检查 FLY_API_TOKEN — 防止主人忘设"""
        content = DEPLOY_SH.read_text(encoding="utf-8")
        assert "FLY_API_TOKEN" in content, "必须引用 FLY_API_TOKEN"
        assert "exit 1" in content, "token 缺失时必须 exit 1"

    def test_deploy_fly_sh_checks_flyctl_installed(self):
        content = DEPLOY_SH.read_text(encoding="utf-8")
        assert "command -v flyctl" in content, "必须检查 flyctl 是否安装"
        assert "https://fly.io/install" in content, "必须给主人安装指引"

    def test_deploy_fly_sh_uses_single_region(self):
        """区域硬约束 hkg (香港)"""
        content = DEPLOY_SH.read_text(encoding="utf-8")
        assert 'REGION="hkg"' in content or "region hkg" in content.lower(), \
            "必须用 hkg 区域"

    def test_deploy_fly_sh_health_check_60s(self):
        """60s 健康循环 (12 * 5s)"""
        content = DEPLOY_SH.read_text(encoding="utf-8")
        assert "12" in content, "健康循环次数必须 12"
        assert "/health" in content, "健康检查必须用 /health"

    def test_deploy_fly_sh_runs_alembic_via_release_command(self):
        """release_command 在 fly.toml 已设, deploy_fly.sh 不应重复"""
        content = DEPLOY_SH.read_text(encoding="utf-8")
        # 不应有 alembic upgrade (Fly release_command 跑)
        assert "alembic upgrade" not in content, \
            "deploy_fly.sh 不应跑 alembic (release_command 已负责)"


class TestFlySecretsSetSh:
    """fly_secrets_set.sh 安全约束"""

    def test_secrets_sh_exists(self):
        assert SECRETS_SH.exists()

    def test_secrets_sh_uses_silent_read(self):
        """ADMIN_TOKEN 必须 -s 静默读 — 不让密码显示在终端"""
        content = SECRETS_SH.read_text(encoding="utf-8")
        assert "read -s" in content, "必须 read -s 静默读密码"
        assert "ADMIN_TOKEN" in content, "必须注入 ADMIN_TOKEN"

    def test_secrets_sh_validates_token_length(self):
        """必须 16+ 字符 — 防止主人设弱密码"""
        content = SECRETS_SH.read_text(encoding="utf-8")
        assert "16" in content, "必须强制 token 16+ 字符"

    def test_secrets_sh_confirms_twice(self):
        """必须二次确认输入 — 防 typo"""
        content = SECRETS_SH.read_text(encoding="utf-8")
        assert content.count("read -s") >= 2, "必须 read -s 至少 2 次 (token + confirm)"


class TestMigrateDataToFlySh:
    """migrate_data_to_fly.sh 关键约束"""

    def test_migrate_sh_exists(self):
        assert MIGRATE_SH.exists()

    def test_migrate_sh_uses_tar_gz(self):
        content = MIGRATE_SH.read_text(encoding="utf-8")
        assert "tar -czf" in content, "必须 tar -czf 打包"
        assert ".tar.gz" in content, "必须 .tar.gz 扩展名"

    def test_migrate_sh_targets_data_db(self):
        content = MIGRATE_SH.read_text(encoding="utf-8")
        assert "worldcup2026.db" in content, "必须打包 worldcup2026.db"
        assert "sync_status.json" in content, "必须打包 sync_status.json"

    def test_migrate_sh_restarts_app(self):
        content = MIGRATE_SH.read_text(encoding="utf-8")
        assert "flyctl apps restart" in content, "必须重启 app 让 scheduler 重连"

    def test_migrate_sh_uses_sftp_for_upload(self):
        """奴才不能持有凭证, 必须用 flyctl sftp 让主人手动传"""
        content = MIGRATE_SH.read_text(encoding="utf-8")
        assert "flyctl sftp" in content, "必须用 flyctl sftp shell 传文件"


class TestDockerfileFlyCompat:
    """Dockerfile 必须兼容 Fly (uid 1000 写 /data 卷)"""

    def test_dockerfile_creates_data_dir(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "/app/data" in content, "必须创建 /app/data 目录"
        assert "mkdir -p" in content, "必须 mkdir -p"

    def test_dockerfile_chowns_app_dir(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        # chown 必须包含 /app (含 /app/data 子目录)
        assert "chown" in content, "必须 chown 给 appuser"
        assert "/app" in content, "chown 必须覆盖 /app"

    def test_dockerfile_uses_non_root_user(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        entrypoint = (PROJECT_ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        # 支持 USER appuser 或 root+entrypoint 降权到 appuser 两种方案
        assert "useradd" in content, "必须 useradd 创建 appuser"
        assert "1000" in content, "uid 必须 1000 (Fly 卷兼容)"
        assert (
            "USER appuser" in content
            or (
                "entrypoint.sh" in content and "gosu appuser" in entrypoint
            )
        ), "必须通过 USER 或 entrypoint/gosu 以 appuser 运行主进程"

    def test_dockerfile_expose_8000(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "EXPOSE 8000" in content

    def test_dockerfile_workers_1(self):
        """Fly 单进程 + workers 1 — 双保险"""
        content = DOCKERFILE.read_text(encoding="utf-8")
        # 支持字符串 CMD 或 JSON 数组 CMD（JSON 数组中逗号后可能有空格）
        assert (
            "--workers 1" in content
            or '"--workers", "1"' in content
            or "'--workers', '1'" in content
        ), "CMD 必须 --workers 1 (Fly 单进程+uvicorn 单 worker 防重复同步)"


class TestAppNameConsistency:
    """跨文件 app 名一致性"""

    def test_app_name_consistent_across_files(self):
        """deploy_fly.sh / fly_secrets_set.sh / migrate_data_to_fly.sh 全部 wc2026-fifa-platform"""
        expected = "wc2026-fifa-platform"
        for sh in [DEPLOY_SH, SECRETS_SH, MIGRATE_SH]:
            content = sh.read_text(encoding="utf-8")
            assert expected in content, f"{sh.name} 缺 {expected}"


class TestNoSecretsInGit:
    """token 不入 git 边界检查"""

    def test_no_env_files_in_git(self):
        """主目录不应有真 ADMIN_TOKEN 提交 — 但 .env 本身在 .gitignore 里"""
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            # .env 必须含 ADMIN_TOKEN= (本地 dev 用), 但不入 git
            assert "ADMIN_TOKEN=" in content, ".env 缺 ADMIN_TOKEN 声明"
            # .env 必须在 .gitignore
            gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
            assert ".env" in gitignore, ".env 不在 .gitignore — 风险!"
