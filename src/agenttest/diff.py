"""diff：两次运行的行为差异，四类（docs/DESIGN.md 第 5 节）。

比的是行为不是文本：新增 / 缺失 / 顺序变化 / 成本变化。
"""

from __future__ import annotations

import re
from collections import Counter

from . import events as ev
from .assertions import format_call

BACKTICK = chr(96)
_QUOTED = re.compile("['\"]([^'\"\n]{3,40})['\"]")
_ERROR_TOKEN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*Error)\b")

TITLE = "行为差异"
NEW, MISSING, ORDER, COST = "新增", "缺失", "顺序", "成本"
SIGNS = {NEW: "+", MISSING: "-", ORDER: "~"}


def quote_tokens(events) -> list:
    """模型输出里引用到的报错关键字（KeyError、quote_error 之类）。"""
    seen: list = []
    for event in events:
        if event.get("type") != "model.result":
            continue
        text = str(event.get("text") or "").replace(BACKTICK, "'")
        for match in _ERROR_TOKEN.findall(text):
            if match not in seen:
                seen.append(match)
        for match in _QUOTED.findall(text):
            token = match.strip()
            if token and token not in seen and not token.startswith("src/"):
                seen.append(token)
    return seen


def call_sequence(events) -> list:
    return [format_call(e) for e in events if e.get("type") == "tool.call"]


def _expand(counter: Counter, order: list) -> list:
    out: list = []
    for item in order:
        if counter.get(item, 0) > 0:
            out.append(item)
            counter[item] -= 1
    return out


def multiset_diff(before: list, after: list) -> tuple:
    """返回 (新增, 缺失)，各自保持原始顺序。"""
    left, right = Counter(before), Counter(after)
    return _expand(right - left, after), _expand(left - right, before)


def order_change(before: list, after: list) -> str | None:
    shared = Counter(before) & Counter(after)
    common_before = _expand(Counter(shared), before)
    common_after = _expand(Counter(shared), after)
    if common_before == common_after:
        return None
    limit = min(len(common_before), len(common_after))
    for index in range(limit):
        if common_before[index] != common_after[index]:
            if index == 0:
                return (
                    "开头是 "
                    + common_before[0]
                    + "，现在开头是 "
                    + common_after[0]
                )
            return (
                common_before[index - 1]
                + " → "
                + common_before[index]
                + " 变成了 "
                + common_after[index - 1]
                + " → "
                + common_after[index]
            )
    return common_before[limit - 1] + " 之后被重排"


def cost_breakdown(events: list) -> dict:
    results = [e for e in events if e.get("type") == "model.result"]
    tokens_in = sum(int((e.get("usage") or {}).get("in", 0) or 0) for e in results)
    tokens_out = sum(int((e.get("usage") or {}).get("out", 0) or 0) for e in results)
    duration = round(
        float(ev.run_end(events).get("t", 0.0)) - float(ev.run_start(events).get("t", 0.0)), 3
    )
    return {
        "tokens": tokens_in + tokens_out,
        "duration": duration,
        "tool_calls": len(ev.tool_calls(events)),
    }


def _pct(before: float, after: float) -> str:
    if before == 0:
        return "新增" if after else "持平"
    return "{:+.0f}%".format((after - before) / before * 100)


def _section(kind: str, items: list) -> list:
    sign = SIGNS.get(kind, " ")
    if not items:
        return ["  " + sign + " " + kind + "  （无）"]
    return ["  " + sign + " " + kind + "  " + item for item in items]


def diff_runs(before_events: list, after_events: list, before_label: str, after_label: str) -> str:
    added, missing = multiset_diff(call_sequence(before_events), call_sequence(after_events))
    tokens_added, tokens_missing = multiset_diff(
        quote_tokens(before_events), quote_tokens(after_events)
    )
    order = order_change(call_sequence(before_events), call_sequence(after_events))
    cost_before = cost_breakdown(before_events)
    cost_after = cost_breakdown(after_events)

    lines = [TITLE + " (" + before_label + " → " + after_label + ")"]
    lines += _section(NEW, ["调用 " + item for item in added] + ["引用 " + t for t in tokens_added])
    lines += _section(
        MISSING, ["调用 " + item for item in missing] + ["引用 " + t for t in tokens_missing]
    )
    lines += _section(ORDER, [order] if order else [])
    lines.append(
        "  {}   tokens {} → {} ({}) · 耗时 {}s → {}s · 工具调用 {} → {}".format(
            COST,
            "{:,}".format(cost_before["tokens"]),
            "{:,}".format(cost_after["tokens"]),
            _pct(cost_before["tokens"], cost_after["tokens"]),
            cost_before["duration"],
            cost_after["duration"],
            cost_before["tool_calls"],
            cost_after["tool_calls"],
        )
    )
    return "\n".join(lines)
