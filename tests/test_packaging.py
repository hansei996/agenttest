"""打包：pyproject 元数据 + console script 入口。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path


def load_pyproject(repo):
    with open(repo / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)


def console_script():
    found = shutil.which("agenttest")
    if found:
        return Path(found)
    scripts = Path(sysconfig.get_path("scripts"))
    for name in ("agenttest.exe", "agenttest", "agenttest-script.py"):
        candidate = scripts / name
        if candidate.exists():
            return candidate
    return None


def clean_env():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_metadata_is_installable_and_dependency_free(repo):
    data = load_pyproject(repo)
    project = data["project"]
    assert project["name"] == "agenttest"
    assert project["version"] == "0.1.0"
    assert project["dependencies"] == []
    assert project["scripts"] == {"agenttest": "agenttest.cli:main"}
    assert data["build-system"]["build-backend"] == "setuptools.build_meta"
    assert data["tool"]["setuptools"]["package-dir"][""] == "src"


def test_package_lives_under_src(src):
    assert (src / "agenttest" / "__init__.py").is_file()
    assert (src / "agenttest" / "cli.py").is_file()


def test_entry_point_is_callable():
    from agenttest.cli import main

    assert callable(main)


def test_module_entry_point_help(repo):
    proc = subprocess.run(
        [sys.executable, "-m", "agenttest", "--help"],
        cwd=str(repo),
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0
    assert "record" in proc.stdout and "stat" in proc.stdout


def test_console_script_help_without_pythonpath(repo):
    launcher = console_script()
    if launcher is None:
        return  # 没安装就跳过；CI 里会 pip install -e . 后真跑
    proc = subprocess.run(
        [str(launcher), "--help"],
        cwd=str(repo),
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    assert "record" in proc.stdout and "replay" in proc.stdout


def test_console_script_replay_without_pythonpath(repo, examples):
    launcher = console_script()
    if launcher is None:
        return
    proc = subprocess.run(
        [str(launcher), "replay", str(examples / "good"), "--assert", "before:quote_error"],
        cwd=str(repo),
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout and "个断言全部通过" in proc.stdout
