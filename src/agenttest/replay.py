"""replay 引擎（docs/DESIGN.md 第 3 节）。

replay 不是"模拟"：agent 真的跑、工具真的执行、文件真的改；
唯一的区别是模型输出全部来自 cassette，且网络被守卫拦住。
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import assertions as asrt
from . import events as ev
from .agent import MODE_REPLAY
from .cassette import cassette_path, read_cassette, read_events_file
from .process import ProcessError, child_env, resolve_argv, resolve_cwd, resolve_workdir

EXHAUSTED_MARK = "model.result 已用尽"
NETWORK_MARK = "NETWORK GUARD"


class ReplayError(RuntimeError):
    """replay 失败：行为漂移、模型输出耗尽、被网络守卫拦住、产物不一致。"""


@dataclass
class ReplayOutcome:
    target: str
    recorded: list = field(default_factory=list)
    events: list = field(default_factory=list)
    results: list = field(default_factory=list)
    child_argv: list = field(default_factory=list)

    @property
    def failed(self) -> list:
        return [r for r in self.results if not r.ok]

    @property
    def ok(self) -> bool:
        return not self.failed


def replay(target: str | Path, assert_exprs: list[str] | None = None) -> ReplayOutcome:
    """跑一次 replay；结构性失败抛 ReplayError，断言失败落在 outcome 里。"""
    path = cassette_path(target)
    recorded = read_cassette(path)
    start = ev.run_start(recorded)
    argv = resolve_argv(list(start.get("argv") or []))
    cwd = resolve_cwd(start, Path(path))

    with tempfile.TemporaryDirectory(prefix="agenttest-replay-") as tmp:
        events_file = Path(tmp) / "events.jsonl"
        env = child_env(MODE_REPLAY, events_file, path)
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise ProcessError("起不来 agent 子进程：" + repr(argv) + "：" + str(exc)) from exc
        if proc.returncode != 0:
            raise ReplayError(_explain_failure(proc, path))
        observed = read_events_file(events_file) if events_file.exists() else []
        if not observed:
            raise ReplayError(
                "agent 没有吐出任何事件（"
                + " ".join(argv)
                + "）：cassette 无法校验，检查它是否用了 agenttest.agent.Session"
            )

    _compare(recorded, observed, path)
    _check_files(recorded, observed, start, cwd, path)
    outcome = ReplayOutcome(
        target=str(target), recorded=recorded, events=observed, child_argv=argv
    )
    outcome.results = asrt.evaluate_all(assert_exprs or [], observed)
    return outcome


def _explain_failure(proc: subprocess.CompletedProcess, path: Path) -> str:
    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    if EXHAUSTED_MARK in stderr:
        return (
            "model.result 耗尽，replay 失败（"
            + str(path)
            + "）："
            + _tail(stderr, EXHAUSTED_MARK)
            + "\n这是行为漂移：cassette 里没有更多模型输出了，而 agent 还在请求。"
        )
    if NETWORK_MARK in stderr:
        return (
            "网络守卫拦住了真实出网，replay 失败（"
            + str(path)
            + "）："
            + _tail(stderr, NETWORK_MARK)
        )
    detail = stderr or stdout or "（子进程没有任何输出）"
    return (
        "agent 子进程退出码 "
        + str(proc.returncode)
        + "，replay 失败（"
        + str(path)
        + "）：\n"
        + "\n".join(detail.splitlines()[-15:])
    )


def _tail(text: str, marker: str) -> str:
    for line in text.splitlines():
        if marker in line:
            return line.strip()
    return text.splitlines()[-1].strip() if text else ""


def _compare(recorded: list, observed: list, path: Path) -> None:
    """逐事件比较行为：时间戳与环境字段不算行为。"""
    for index, (want, got) in enumerate(zip(recorded, observed)):
        a, b = ev.strip_volatile(want), ev.strip_volatile(got)
        if a == b:
            continue
        raise ReplayError(
            "行为漂移：第 "
            + str(index + 1)
            + " 个事件（"
            + str(want.get("type"))
            + "）与 cassette 不一致（"
            + str(path)
            + "）："
            + _first_diff(a, b)
        )
    if len(recorded) != len(observed):
        raise ReplayError(
            "行为漂移：cassette 记录 "
            + str(len(recorded))
            + " 个事件，这次跑了 "
            + str(len(observed))
            + " 个（"
            + str(path)
            + "），从第 "
            + str(min(len(recorded), len(observed)) + 1)
            + " 个事件开始分叉"
        )


def _first_diff(a: dict, b: dict) -> str:
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            return "字段 " + key + "：记录 " + _brief(a.get(key)) + "，实际 " + _brief(b.get(key))
    return "内容不同"


def _brief(value, limit: int = 120) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _check_files(recorded: list, observed: list, start: dict, cwd: Path, path: Path) -> None:
    """结束时对比"实际改动 == 记录改动"（DESIGN 第 3 节）。"""
    want = dict(ev.run_end(recorded).get("files") or {})
    if not want:
        return
    workdir = resolve_workdir(start, cwd)
    if not workdir.is_dir():
        raise ReplayError(
            "产物校验失败：cassette 记录的工作目录 "
            + str(workdir)
            + " 不存在，无法比对实际产物（"
            + str(path)
            + "）"
        )
    got = {name: _sha256(workdir / name) for name in want}
    if got != want:
        lines = [
            name + ": 记录 " + str(want[name]) + "，实际 " + str(got.get(name))
            for name in want
            if want[name] != got.get(name)
        ]
        raise ReplayError(
            "产物不一致：实际改动与 cassette 记录的改动不同（"
            + str(path)
            + "）：\n"
            + "\n".join(lines)
        )
    recorded_changed = list(ev.run_end(recorded).get("files_changed") or [])
    actual_changed = list(ev.run_end(observed).get("files_changed") or [])
    if actual_changed != recorded_changed:
        raise ReplayError(
            "产物不一致：cassette 记录的 files_changed 是 "
            + str(recorded_changed)
            + "，这次是 "
            + str(actual_changed)
        )


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
