"""测试的公共设施：把 src/ 塞进 sys.path，并提供跑 CLI 的助手。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def cli_env() -> dict:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else str(SRC) + os.pathsep + existing
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agenttest", *args],
        cwd=str(cwd or REPO),
        env=cli_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


@pytest.fixture(scope="session")
def src() -> Path:
    return SRC


@pytest.fixture(scope="session")
def examples() -> Path:
    return REPO / "examples"


@pytest.fixture(scope="session")
def run() -> "callable":
    return run_cli
