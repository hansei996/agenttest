"""record：跑一次真实的 agent，把事件流落成 cassette（DESIGN 第 2 节）。"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import events as ev
from .agent import MODE_RECORD
from .cassette import read_events_file, write_cassette
from .process import child_env


class RecordError(RuntimeError):
    """录制失败。"""


@dataclass
class RecordOutcome:
    target: str
    cassette: str
    events: list = field(default_factory=list)

    @property
    def counts(self) -> dict:
        counts: dict = {}
        for event in self.events:
            counts[event["type"]] = counts.get(event["type"], 0) + 1
        return counts


def record(
    target: str | Path,
    command: list[str],
    cwd: str | Path | None = None,
) -> RecordOutcome:
    """跑 command，把它的全部事件写成 <target>/cassette.jsonl。"""
    if not command:
        raise RecordError("record 需要一个要录制的命令：... record <dir> -- <command>")
    directory = Path(target)
    directory.mkdir(parents=True, exist_ok=True)
    workdir = Path(cwd) if cwd else Path.cwd()

    with tempfile.TemporaryDirectory(prefix="agenttest-record-") as tmp:
        events_file = Path(tmp) / "events.jsonl"
        env = child_env(MODE_RECORD, events_file)
        try:
            proc = subprocess.run(
                command,
                cwd=str(workdir),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise RecordError("起不来 agent 子进程：" + repr(command) + "：" + str(exc)) from exc
        if not events_file.exists():
            raise RecordError(
                "没录到任何事件："
                + " ".join(command)
                + " 退出码 "
                + str(proc.returncode)
                + "。agent 必须用 agenttest.agent.Session 说话。stderr：\n"
                + (proc.stderr or "").strip()[-2000:]
            )
        events = read_events_file(events_file)

    if not events:
        raise RecordError("事件文件是空的，没有可录的东西")
    for event in events:
        ev.validate(event)
    if events[0]["type"] != "run.start":
        raise RecordError("第一个事件必须是 run.start，实际是 " + str(events[0]["type"]))
    if events[-1]["type"] != "run.end":
        raise RecordError(
            "最后一个事件必须是 run.end，实际是 "
            + str(events[-1]["type"])
            + "（agent 没有调用 finish()）"
        )
    path = write_cassette(directory, events)
    return RecordOutcome(target=str(target), cassette=str(path), events=events)


def record_summary(outcome: RecordOutcome) -> str:
    parts = ", ".join(name + " " + str(n) for name, n in outcome.counts.items())
    return (
        "recorded "
        + outcome.target
        + " -> "
        + outcome.cassette
        + "\n  "
        + str(len(outcome.events))
        + " 个事件（"
        + parts
        + "）"
    )
