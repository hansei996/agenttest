"""打包：pyproject 元数据 + console script 入口。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path

import agenttest
import pytest


def load_pyproject(repo):
    with open(repo / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)


def console_script():
    # 允许钉死 launcher 路径（CI 用，也让「没安装」这条能被测）
    pinned = os.environ.get("AGENTTEST_LAUNCHER")
    if pinned:
        candidate = Path(pinned)
        return candidate if candidate.exists() else None
    found = shutil.which("agenttest")
    if found:
        return Path(found)
    scripts = Path(sysconfig.get_path("scripts"))
    for name in ("agenttest.exe", "agenttest", "agenttest-script.py"):
        candidate = scripts / name
        if candidate.exists():
            return candidate
    return None


def require_console_script():
    """找不到 launcher 必须 FAIL（不是 return、不是 skip）。

    「没安装 -> 静默 return」曾让这两条测试长期假绿：pytest 显示绿点、连 skip 标记都没有，
    而本机 agenttest 命令从未生成过。装完即用是本项目的核心承诺，不能这样自欺。
    """
    launcher = console_script()
    if launcher is None:
        pytest.fail(
            "找不到 agenttest 命令：先跑 python -m pip install -e ."
            "（构建隔离需联网拉 setuptools），或 --no-build-isolation 配合已有 setuptools。脚本目录："
            + str(sysconfig.get_path("scripts"))
        )
    return launcher


def clean_env():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_metadata_is_installable_and_dependency_free(repo):
    data = load_pyproject(repo)
    project = data["project"]
    assert project["name"] == "agenttest"
    # 版本号只校验"合法 + 两处一致"，不钉死具体数字：
    # 钉死会让每次发版都把测试弄红，而真正该防的是 pyproject 与包内 __version__ 漂移。
    assert re.fullmatch(r"\d+\.\d+\.\d+", project["version"])
    assert project["version"] == agenttest.__version__
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
    launcher = require_console_script()
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
    launcher = require_console_script()
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

def test_missing_launcher_fails_loudly(monkeypatch):
    """回归测试：launcher 不存在时必须 FAIL。

    防的是历史缺陷——原来写的是 if launcher is None: return，pytest 显示绿点、
    连 skip 都没有，于是「装完即用」从未被真验证过。
    """
    monkeypatch.setenv("AGENTTEST_LAUNCHER", str(Path("definitely-not-here") / "agenttest.exe"))
    with pytest.raises(pytest.fail.Exception):
        require_console_script()
