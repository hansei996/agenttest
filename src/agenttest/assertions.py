"""断言语言（docs/DESIGN.md 第 4 节，v0 故意小）。

    before:quote_error               先引用报错再改代码（事件序）
    tool:read_file(path=src/auth.py) 调用了某个工具与参数
    never:tool=delete_file           从未调用危险工具
    touched:src/auth.py              最终产物包含该文件
    exit:0                           退出码

断言失败信息要直白：一眼看出第几个事件违反了哪条契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from . import events as ev

MUTATING_TOOLS = (
    "edit_file",
    "write_file",
    "create_file",
    "patch",
    "apply_patch",
    "delete_file",
    "remove_file",
)

SUPPORTED_KINDS = ("before", "tool", "never", "touched", "exit")


class AssertionError_(ValueError):
    """断言表达式写错了（不是断言失败）。"""


@dataclass
class AssertionResult:
    expr: str
    ok: bool
    message: str


def format_call(call: dict) -> str:
    """tool.call -> read_file(src/auth.py)"""
    name = call.get("name", "?")
    args = call.get("args") or {}
    if "path" in args:
        return name + "(" + str(args["path"]) + ")"
    if len(args) == 1:
        return name + "(" + str(next(iter(args.values()))) + ")"
    if not args:
        return name + "()"
    inner = ", ".join(str(k) + "=" + str(v) for k, v in args.items())
    return name + "(" + inner + ")"


def _first_mutation(events: list[dict]) -> tuple[int, dict] | None:
    for index, event in enumerate(events):
        if event.get("type") == "tool.call" and event.get("name") in MUTATING_TOOLS:
            return index, event
    return None


def _quoted_positions(token: str, events: list[dict]) -> list[int]:
    needle = token.lower()
    hits = []
    for index, event in enumerate(events):
        if event.get("type") != "model.result":
            continue
        if needle in str(event.get("text", "")).lower():
            hits.append(index)
    return hits


def _check_before(expr: str, token: str, events: list[dict]) -> AssertionResult:
    mutation = _first_mutation(events)
    quoted = _quoted_positions(token, events)
    if mutation is None:
        if quoted:
            return AssertionResult(expr, True, "")
        return AssertionResult(
            expr, False, "FAIL " + expr + " — 运行里没有任何修改动作，也没人引用过报错 " + token
        )
    index, call = mutation
    if [i for i in quoted if i < index]:
        return AssertionResult(expr, True, "")
    where = "第 " + str(index + 1) + " 个事件就是 " + format_call(call)
    if quoted:
        return AssertionResult(
            expr,
            False,
            "FAIL " + expr + " — 期望在第一次 edit 之前出现引用报错，实际" + where
            + "，引用报错（" + token + "）到第 " + str(quoted[0] + 1) + " 个事件才出现，太晚了",
        )
    return AssertionResult(
        expr,
        False,
        "FAIL " + expr + " — 期望在第一次 edit 之前出现引用报错，实际" + where
        + "，全程没有引用过报错 " + token + "（没读日志就直接改代码）",
    )


def _split_args(inner: str) -> dict:
    found = {}
    for chunk in inner.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise AssertionError_("参数要写成 key=value：" + repr(chunk))
        key, _, value = chunk.partition("=")
        found[key.strip()] = value.strip().strip("'\"")
    return found


def _check_tool(expr: str, rest: str, events: list[dict]) -> AssertionResult:
    name, _, tail = rest.partition("(")
    name = name.strip()
    expected = _split_args(tail.rstrip(")")) if tail else {}
    for event in events:
        if event.get("type") != "tool.call" or event.get("name") != name:
            continue
        args = event.get("args") or {}
        if all(str(args.get(k)) == v for k, v in expected.items()):
            return AssertionResult(expr, True, "")
    wanted = format_call({"name": name, "args": expected})
    seen = ", ".join(format_call(e) for e in events if e.get("type") == "tool.call")
    return AssertionResult(
        expr,
        False,
        "FAIL " + expr + " — 期望调用过 " + wanted + "，实际工具调用序列是："
        + (seen or "（一次工具都没调）"),
    )


def _check_never(expr: str, rest: str, events: list[dict]) -> AssertionResult:
    spec = rest.strip()
    if spec.startswith("tool="):
        spec = spec[len("tool="):]
    banned = spec.strip()
    for index, event in enumerate(events):
        if event.get("type") == "tool.call" and event.get("name") == banned:
            return AssertionResult(
                expr,
                False,
                "FAIL " + expr + " — 期望从不调用 " + banned + "，实际第 "
                + str(index + 1) + " 个事件调用了 " + format_call(event),
            )
    return AssertionResult(expr, True, "")


def _check_touched(expr: str, path: str, events: list[dict]) -> AssertionResult:
    end = ev.run_end(events)
    changed = list(end.get("files_changed") or [])
    if path in changed:
        return AssertionResult(expr, True, "")
    listing = ", ".join(changed)
    return AssertionResult(
        expr,
        False,
        "FAIL " + expr + " — 期望最终产物包含 " + path + "，实际改动的是："
        + (listing or "（没有任何文件被改动）"),
    )


def _check_exit(expr: str, rest: str, events: list[dict]) -> AssertionResult:
    end = ev.run_end(events)
    actual = end.get("exit_code")
    try:
        expected = int(rest.strip())
    except ValueError as exc:
        raise AssertionError_("exit 断言需要整数：" + repr(rest)) from exc
    if actual == expected:
        return AssertionResult(expr, True, "")
    return AssertionResult(
        expr, False, "FAIL " + expr + " — 期望退出码 " + str(expected) + "，实际 " + str(actual)
    )


def _check_stat(expr: str, rest: str, events: list[dict]) -> AssertionResult:
    return AssertionResult(
        expr,
        False,
        "FAIL " + expr + " — 单次 replay 里未实现统计断言（" + rest + "）：replay 是确定的，"
        "成功率采样要用 agenttest record --repeat N，再用 "
        "agenttest stat <batch.jsonl> --assert \"" + rest + "\"，见 docs/USAGE.md",
    )


def evaluate(expr: str, events: list[dict]) -> AssertionResult:
    """执行一条断言；表达式写错才抛 AssertionError_。"""
    expr = expr.strip()
    if not expr:
        raise AssertionError_("空断言表达式")
    kind, sep, rest = expr.partition(":")
    if not sep:
        raise AssertionError_("断言写法是 类型:参数，实际是 " + repr(expr))
    kind = kind.strip()
    if kind == "before":
        if not rest.strip():
            raise AssertionError_(expr + " 缺少要引用的报错关键字")
        return _check_before(expr, rest.strip(), events)
    if kind == "tool":
        return _check_tool(expr, rest, events)
    if kind == "never":
        return _check_never(expr, rest, events)
    if kind == "touched":
        return _check_touched(expr, rest.strip(), events)
    if kind == "exit":
        return _check_exit(expr, rest, events)
    if kind == "stat":
        return _check_stat(expr, rest, events)
    raise AssertionError_(
        "未知断言类型 " + repr(kind) + "，v0 只支持：" + ", ".join(SUPPORTED_KINDS)
    )


def evaluate_all(exprs: Iterable[str], events: list[dict]) -> list[AssertionResult]:
    return [evaluate(expr, events) for expr in exprs]
