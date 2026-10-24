"""emit —— 生产端最小 SDK：不用 record / replay，也能写出合规 cassette。

为什么要它：格式扩散的唯一引擎是「生产成本足够低」。消费者（我们的 replay/diff/regress）
只有先有人愿意产出 cassette 才有意义。这里给出 20 行就能写完的一条路：

    from agenttest import emit

    run = emit.Run(agent="my-agent", argv=["python", "agent.py"])
    run.model_result("先看日志", tool_calls=[{"name": "read_file", "args": {"path": "logs/app.log"}}])
    run.tool_result("read_file", ok=True, bytes=66)
    run.end(exit_code=0)
    run.write("runs/fix-auth")          # 写出 <dir>/cassette.jsonl（带哈希链）

写出复用 agenttest.cassette.write_cassette —— 没有第二种磁盘格式。
"""
from __future__ import annotations

import time
from pathlib import Path

from . import events as _events
from .cassette import write_cassette


class EmitError(ValueError):
    """生产者用错了 API（例如没 start 就 end）。"""


class Run:
    """按顺序攒事件，最后一次性写出。"""

    def __init__(self, agent: str, argv: list[str] | None = None, cwd: str = ".", env_fingerprint: str | None = None):
        self.events: list[dict] = []
        self.started = False
        self.ended = False
        self._t0 = time.time()
        self._start(agent, argv or [], cwd, env_fingerprint)

    def _now(self) -> float:
        return round(time.time() - self._t0, 3)

    def _append(self, event: dict) -> dict:
        if self.ended:
            raise EmitError("run 已经 end()，不能再追加事件")
        event.setdefault("t", self._now())
        self.events.append(event)
        return event

    def _start(self, agent: str, argv: list[str], cwd: str, env_fingerprint: str | None) -> None:
        event = {
            "type": "run.start",
            "agent": agent,
            "argv": list(argv),
            "cwd": cwd,
            "env_fingerprint": env_fingerprint or _events.env_fingerprint(),
        }
        self._append(event)
        self.started = True

    def model_call(self, messages: list, tools: list | None = None, model: str | None = None) -> dict:
        event = {
            "type": "model.call",
            "model": model or "unknown",
            "request": {"messages": list(messages), "tools": list(tools or [])},
        }
        return self._append(event)

    def model_result(self, text: str, tool_calls: list | None = None, usage: dict | None = None, model: str | None = None) -> dict:
        event = {
            "type": "model.result",
            "text": text,
            "tool_calls": list(tool_calls or []),
            "usage": dict(usage or {"in": 0, "out": 0}),
        }
        if model:
            event["model"] = model
        return self._append(event)

    def tool_call(self, name: str, args: dict | None = None) -> dict:
        return self._append({"type": "tool.call", "name": name, "args": dict(args or {})})

    def tool_result(self, name: str, ok: bool = True, **extra) -> dict:
        event = {"type": "tool.result", "name": name, "ok": bool(ok), "bytes": int(extra.pop("bytes", 0))}
        event.update(extra)
        return self._append(event)

    def end(self, exit_code: int = 0, files: dict | None = None) -> dict:
        if not self.started:
            raise EmitError("必须先有一个 run")
        event = self._append({
            "type": "run.end",
            "exit_code": int(exit_code),
            "files_changed": sorted(dict(files or {}).keys()),
        })
        self.ended = True
        return event

    def write(self, target: str | Path) -> Path:
        if not self.ended:
            raise EmitError("写出前必须先 end()：cassette 需要 run.end 收尾")
        return write_cassette(target, self.events)