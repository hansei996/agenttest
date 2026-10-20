"""agent 侧的 SDK：把 agent 抓到的事件吐给 agenttest。

任何 agent 只要通过这个 Session 说话，就能被 record / replay 测到——
适配器是插件（docs/DESIGN.md 第 6 节），v0.1 内置的适配器就是"事件协议"本身。

    ctx = Session(agent="my_agent", workdir=".work/run1")
    reply = ctx.model(messages, provider=my_model)     # record 真调；replay 来自 cassette
    ctx.tool("read_file", {"path": "a.py"}, read_file) # 真实执行，只记录
    ctx.finish(exit_code=0, files_changed=["a.py"])
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from . import events as ev
from . import guard
from .cassette import read_cassette

ENV_MODE = "AGENTTEST_MODE"
ENV_EVENTS = "AGENTTEST_EVENTS"
ENV_CASSETTE = "AGENTTEST_CASSETTE"

MODE_RECORD = "record"
MODE_REPLAY = "replay"


class AgentError(RuntimeError):
    """agent 侧的使用错误。"""


class CassetteExhausted(RuntimeError):
    """cassette 里的 model.result 用完了，而 agent 还想再要一次。"""


@dataclass
class ToolOutcome:
    ok: bool
    output: str


def _posix_relpath(path: Path) -> str:
    """尽量记录相对路径，让 cassette 能跨机器重放。"""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Session:
    """一次运行的事件出口，同时是 replay 时 model.result 的入口。"""

    def __init__(
        self,
        agent: str,
        workdir: str | Path = ".",
        model: str = "scripted",
        argv: list[str] | None = None,
    ) -> None:
        self.mode = os.environ.get(ENV_MODE)
        events_path = os.environ.get(ENV_EVENTS)
        if self.mode not in (MODE_RECORD, MODE_REPLAY) or not events_path:
            raise AgentError(
                "必须在 agenttest 下运行：缺少 "
                + ENV_MODE
                + " / "
                + ENV_EVENTS
                + " 环境变量。请用 python -m agenttest record <dir> -- <command> "
                "或 python -m agenttest replay <dir> 启动。"
            )
        if self.mode == MODE_REPLAY:
            guard.install()
        self.agent = agent
        self.model_name = model
        self.workdir = Path(workdir)
        self._stream = open(events_path, "a", encoding="utf-8")
        self._t0 = time.monotonic()
        self._pending: list[dict] = []
        self._consumed = 0
        self._finished = False
        if self.mode == MODE_REPLAY:
            cassette = os.environ.get(ENV_CASSETTE)
            if not cassette:
                raise AgentError("replay 模式缺少 " + ENV_CASSETTE + " 环境变量")
            self._pending = ev.model_results(read_cassette(cassette))
        self.emit(
            {
                "type": "run.start",
                "agent": agent,
                "argv": argv if argv is not None else _default_argv(),
                "cwd": Path.cwd().resolve().as_posix(),
                "env_fingerprint": ev.env_fingerprint(),
                "workdir": _posix_relpath(self.workdir),
            }
        )

    # -- 事件出口 -------------------------------------------------------
    def emit(self, event: dict) -> dict:
        event = {"t": round(time.monotonic() - self._t0, 4), **event}
        ev.validate(event)
        self._stream.write(ev.canonical(event) + "\n")
        self._stream.flush()
        return event

    # -- 模型边界 -------------------------------------------------------
    def model(
        self,
        messages: list[dict],
        provider: Callable[[dict], dict] | None = None,
        tools: Iterable[str] | None = None,
    ) -> dict:
        """一次模型调用。record 走 provider，replay 按序消费 cassette。"""
        request = {"messages": messages, "tools": list(tools or [])}
        self.emit({"type": "model.call", "model": self.model_name, "request": request})
        if self.mode == MODE_REPLAY:
            if not self._pending:
                raise CassetteExhausted(
                    "model.result 已用尽：已消费 "
                    + str(self._consumed)
                    + " 条，agent 又发起了第 "
                    + str(self._consumed + 1)
                    + " 次模型调用。cassette 里没有更多模型输出了，"
                    "说明 agent 的行为漂移了（它现在比录制时多问了一次模型）。"
                )
            recorded = self._pending.pop(0)
            self._consumed += 1
            result = {
                "type": "model.result",
                "text": recorded.get("text", ""),
                "tool_calls": recorded.get("tool_calls") or [],
                "usage": recorded.get("usage") or {},
            }
        else:
            if provider is None:
                raise AgentError("record 模式必须提供 provider（真实模型调用）")
            reply = provider(request) or {}
            result = {
                "type": "model.result",
                "text": reply.get("text", ""),
                "tool_calls": reply.get("tool_calls") or [],
                "usage": reply.get("usage") or {},
            }
        self.emit(result)
        return {
            "text": result["text"],
            "tool_calls": result["tool_calls"],
            "usage": result["usage"],
        }

    # -- 工具边界 -------------------------------------------------------
    def tool(self, name: str, args: dict, handler: Callable[[dict], Any]) -> ToolOutcome:
        """记录 tool.call / tool.result，工具本身是真实执行的。"""
        self.emit({"type": "tool.call", "name": name, "args": args})
        try:
            produced = handler(args)
            ok = True
            output = produced if isinstance(produced, str) else str(produced)
        except Exception as exc:  # 工具失败也是可观测行为
            ok = False
            output = type(exc).__name__ + ": " + str(exc)
        self.emit(
            {
                "type": "tool.result",
                "name": name,
                "ok": ok,
                "bytes": len(output.encode("utf-8")),
            }
        )
        return ToolOutcome(ok=ok, output=output)

    # -- 收尾 -----------------------------------------------------------
    def finish(
        self, exit_code: int = 0, files_changed: Iterable[str] | None = None
    ) -> dict:
        if self._finished:
            raise AgentError("finish() 只能调用一次")
        self._finished = True
        paths = [Path(p).as_posix() for p in (files_changed or [])]
        files = {p: _sha256_file(self.workdir / p) for p in paths}
        event = self.emit(
            {
                "type": "run.end",
                "exit_code": exit_code,
                "files_changed": paths,
                "files": files,
            }
        )
        self._stream.close()
        return event


def _default_argv() -> list[str]:
    return ["python", _posix_relpath(Path(sys.argv[0]))] + list(sys.argv[1:])
