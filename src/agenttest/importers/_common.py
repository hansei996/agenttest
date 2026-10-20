"""导入器的公共骨架：把各格式解析出的 Exchange 装配成 6 类事件。

这里只负责三件事：事件装配、时间戳策略、warning 收集。
磁盘格式不在这里定义——写盘一律复用 agenttest.cassette.write_cassette，
导入器不引入第二种 cassette 格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..cassette import write_cassette

SYNTHETIC_STEP = 0.1
DEFAULT_AGENT = "imported"


class ImporterError(ValueError):
    """输入不是受支持的日志格式，或损坏到无法导入。"""


@dataclass
class Warnings:
    """按出现顺序收集、去掉完全重复的一条，保证两次导入结果一致。"""

    items: list = field(default_factory=list)

    def add(self, message: str) -> None:
        if message not in self.items:
            self.items.append(message)


@dataclass
class Exchange:
    """一轮 request/response 的规范化结果，是各格式解析器的统一出口。"""

    context: list = field(default_factory=list)
    model: str = "unknown"
    tools: list = field(default_factory=list)
    text: str = ""
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    timestamp: float | None = None


@dataclass
class Cassette:
    """导入结果：事件流 + 可核验的 warning 清单。直接 write() 就能落盘。"""

    events: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    source: str = ""
    format: str = ""
    synthetic_timestamps: bool = False

    def write(self, target: str | Path) -> Path:
        """写 <target>/cassette.jsonl，哈希链由 cassette 模块生成。"""
        return write_cassette(target, self.events)

    @property
    def counts(self) -> dict:
        counts: dict = {}
        for event in self.events:
            counts[event["type"]] = counts.get(event["type"], 0) + 1
        return counts


def _collect_results(exchanges):
    """先把所有 tool_result 收齐：回执通常出现在下一轮的 request 里。"""
    by_id: dict = {}
    by_name: dict = {}
    for exchange in exchanges:
        for message in exchange.context:
            for result in message.get("tool_results") or ():
                if result.get("id"):
                    by_id.setdefault(result["id"], result)
                else:
                    by_name.setdefault(result.get("name") or "", []).append(result)
    return by_id, by_name


def _take_result(call, by_id, by_name):
    call_id = call.get("id")
    if call_id and call_id in by_id:
        return by_id.pop(call_id)
    queue = by_name.get(call.get("name") or "")
    if queue:
        return queue.pop(0)
    return None


def build_cassette(exchanges, *, fmt, source, warnings, exit_code=None):
    """把 Exchange 列表装配成 Cassette（事件 + warnings + 时间戳策略）。"""
    if not exchanges:
        raise ImporterError("没有解析出任何一轮对话，无法生成 cassette")

    by_id, by_name = _collect_results(exchanges)
    events: list = []
    groups: list = []

    def emit(event, group):
        events.append(event)
        groups.append(group)

    for index, exchange in enumerate(exchanges):
        emit(
            {
                "type": "model.call",
                "model": exchange.model,
                "request": {"messages": exchange.context, "tools": list(exchange.tools)},
            },
            index,
        )
        emit(
            {
                "type": "model.result",
                "text": exchange.text,
                "tool_calls": [
                    {"name": call.get("name", ""), "args": call.get("args") or {}}
                    for call in exchange.tool_calls
                ],
                "usage": dict(exchange.usage),
            },
            index,
        )
        for call in exchange.tool_calls:
            emit({"type": "tool.call", "name": call.get("name", ""), "args": call.get("args") or {}}, index)
            result = _take_result(call, by_id, by_name)
            if result is None:
                warnings.add(
                    "tool.call "
                    + str(call.get("name"))
                    + " 没有对应的 tool_result（日志里缺这条工具回执），只记了 tool.call"
                )
                continue
            emit(
                {
                    "type": "tool.result",
                    "name": call.get("name", ""),
                    "ok": bool(result.get("ok", True)),
                    "bytes": int(result.get("bytes") or 0),
                },
                index,
            )

    for leftover in sorted(by_id):
        warnings.add("tool_result id=" + str(leftover) + " 找不到对应的 tool_call，已丢弃")
    for name in sorted(by_name):
        for _ in by_name[name]:
            warnings.add("tool_result name=" + str(name) + " 找不到对应的 tool_call，已丢弃")

    if exit_code is None:
        exit_code = 0
        warnings.add(
            "run.end.exit_code 不在日志里，按 0 记录；需要别的值请用 load(..., exit_code=N)"
        )
    warnings.add(
        "run.end.files_changed 记为空：日志不含产物改动信息，replay 的产物比对会跳过"
    )

    real = [exchange.timestamp for exchange in exchanges]
    synthetic = any(stamp is None for stamp in real)
    if synthetic:
        warnings.add(
            "synthetic timestamps: 日志缺少每轮时间戳，全部 t 由事件序号合成"
            "（t = index * " + str(SYNTHETIC_STEP) + "s），不是真实时间"
        )
        times = [round(index * SYNTHETIC_STEP, 4) for index in range(len(events) + 2)]
    else:
        base = min(float(stamp) for stamp in real)
        offsets = [round(float(stamp) - base, 4) for stamp in real]
        if offsets != sorted(offsets):
            warnings.add("时间戳不是单调递增的，t 按日志原样保留，没有重排")
        tail = round(max(offsets) + SYNTHETIC_STEP, 4) if offsets else SYNTHETIC_STEP
        times = [0.0] + [offsets[group] for group in groups] + [tail]

    start = {
        "type": "run.start",
        "agent": DEFAULT_AGENT + ":" + fmt,
        "argv": [],
        "cwd": ".",
        "env_fingerprint": DEFAULT_AGENT + "|" + fmt,
        "meta": {
            "format": fmt,
            "source": source,
            "synthetic_timestamps": synthetic,
            "warnings": list(warnings.items),
        },
    }
    end = {
        "type": "run.end",
        "exit_code": int(exit_code),
        "files_changed": [],
    }

    ordered = [start] + events + [end]
    for event, stamp in zip(ordered, times):
        event["t"] = stamp
    return Cassette(
        events=ordered,
        warnings=list(warnings.items),
        source=source,
        format=fmt,
        synthetic_timestamps=synthetic,
    )
