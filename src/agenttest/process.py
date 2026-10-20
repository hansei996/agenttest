"""把 agent 作为子进程跑起来：环境变量就是父子之间的协议。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .agent import ENV_CASSETTE, ENV_EVENTS, ENV_MODE, MODE_REPLAY

INTERPRETER_TOKENS = ("python", "python3", "py", "python.exe", "python3.exe", "pythonw.exe")


class ProcessError(RuntimeError):
    """子进程起不来。"""


def package_src_dir() -> str:
    """src/ 目录：让子进程无论如何都能 import agenttest。"""
    return str(Path(__file__).resolve().parents[1])


def child_env(mode: str, events_file: str | Path, cassette_file: str | Path | None = None) -> dict:
    env = os.environ.copy()
    env[ENV_MODE] = mode
    env[ENV_EVENTS] = str(Path(events_file).resolve())
    env.pop(ENV_CASSETTE, None)
    if mode == MODE_REPLAY:
        if cassette_file is None:
            raise ProcessError("replay 模式必须给出 cassette 路径")
        env[ENV_CASSETTE] = str(Path(cassette_file).resolve())
    src = package_src_dir()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONHASHSEED"] = "0"
    return env


def resolve_argv(argv: list[str]) -> list[str]:
    """argv[0] 里的 python 是占位符，永远解析成当前解释器，cassette 才能跨机器重放。"""
    if not argv:
        raise ProcessError("cassette 的 run.start.argv 是空的，无法重放")
    head = Path(str(argv[0])).name.lower()
    if head in INTERPRETER_TOKENS:
        return [sys.executable] + [str(a) for a in argv[1:]]
    return [str(a) for a in argv]


def resolve_cwd(start: dict, cassette_file: Path) -> Path:
    """优先用录制时的 cwd；换机器后按 agent 脚本的相对路径往上找。"""
    recorded = Path(str(start.get("cwd") or "."))
    if recorded.is_dir():
        return recorded
    argv = list(start.get("argv") or [])
    script = argv[1] if len(argv) > 1 else None
    if script and not Path(script).is_absolute():
        for base in [Path(cassette_file).parent, *Path(cassette_file).parents]:
            if (base / script).exists():
                return base
    return Path.cwd()


def resolve_workdir(start: dict, cwd: Path) -> Path:
    path = Path(str(start.get("workdir") or "."))
    return path if path.is_absolute() else (cwd / path)
