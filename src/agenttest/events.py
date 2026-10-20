"""事件模型（docs/DESIGN.md 第 1 节）。

v0 只有这 6 种事件类型，宁少不多。一个事件就是可 JSON 序列化的 dict；
`t` 是相对 run.start 的秒数，只用于成本统计与展示，永远不参与行为比较。
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from typing import Any, Iterable

EVENT_TYPES = (
    "run.start",
    "model.call",
    "model.result",
    "tool.call",
    "tool.result",
    "run.end",
)

REQUIRED_FIELDS = {
    "run.start": ("agent", "argv", "cwd", "env_fingerprint"),
    "model.call": ("model", "request"),
    "model.result": ("text", "tool_calls", "usage"),
    "tool.call": ("name", "args"),
    "tool.result": ("name", "ok", "bytes"),
    "run.end": ("exit_code", "files_changed"),
}

# 比较两次运行的行为时要忽略的字段：时间戳与录制机器的环境。
VOLATILE_FIELDS = {
    "run.start": ("t", "cwd", "env_fingerprint"),
    "*": ("t",),
}


class EventError(ValueError):
    """事件结构非法。"""


def validate(event: Any) -> dict:
    """校验一个事件，返回它本身；不合法则抛 EventError。"""
    if not isinstance(event, dict):
        raise EventError(f"事件必须是 JSON 对象，实际是 {type(event).__name__}")
    etype = event.get("type")
    if etype not in EVENT_TYPES:
        raise EventError(
            f"未知事件类型 {etype!r}，v0 只允许：{', '.join(EVENT_TYPES)}"
        )
    missing = [name for name in REQUIRED_FIELDS[etype] if name not in event]
    if missing:
        raise EventError(f"{etype} 缺少必填字段：{', '.join(missing)}")
    return event


def canonical(obj: Any) -> str:
    """稳定的 JSON 文本：排序键、紧凑分隔符，用于哈希与确定性输出。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def env_fingerprint() -> str:
    return f"py{sys.version_info[0]}.{sys.version_info[1]}|{platform.system().lower()}"


def strip_volatile(event: dict) -> dict:
    """去掉时间戳与环境字段，剩下的才是"行为"。"""
    etype = event.get("type")
    drop = set(VOLATILE_FIELDS.get(etype, ())) | set(VOLATILE_FIELDS["*"])
    return {k: v for k, v in event.items() if k not in drop}


def of_type(events: Iterable[dict], etype: str) -> list[dict]:
    return [e for e in events if e.get("type") == etype]


def model_results(events: Iterable[dict]) -> list[dict]:
    return of_type(events, "model.result")


def tool_calls(events: Iterable[dict]) -> list[dict]:
    return of_type(events, "tool.call")


def run_start(events: Iterable[dict]) -> dict:
    found = of_type(events, "run.start")
    if not found:
        raise EventError("cassette 里没有 run.start，无法重放")
    return found[0]


def run_end(events: Iterable[dict]) -> dict:
    found = of_type(events, "run.end")
    if not found:
        raise EventError("cassette 里没有 run.end，运行没有正常收尾")
    return found[-1]
