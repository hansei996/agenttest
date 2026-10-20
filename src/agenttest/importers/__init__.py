"""importers：把已有的模型日志变成可直接写盘的 cassette。

v0.1 支持两种输入：

* "openai-chat"        Chat Completions 风格的 request/response（JSONL 或 JSON 数组）
* "anthropic-messages" Messages 风格的 content blocks（含 tool_use / tool_result）

    from agenttest.importers import load
    cassette = load("logs/openai.jsonl")   # 自动识别格式
    cassette.write("examples/imported")    # 写 <dir>/cassette.jsonl（哈希链来自 cassette 模块）

日志里没有的东西绝不编造：缺时间戳就按序号合成并在 run.start.meta 里写
synthetic_timestamps: true；映射不了的内容进 meta.warnings，不静默丢弃。
磁盘格式只有一种——写盘复用 agenttest.cassette.write_cassette。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import anthropic, openai
from ._common import Cassette, Exchange, ImporterError, Warnings, build_cassette

OPENAI_CHAT = "openai-chat"
ANTHROPIC_MESSAGES = "anthropic-messages"
FORMATS = (OPENAI_CHAT, ANTHROPIC_MESSAGES)
ALIASES = {
    "openai": OPENAI_CHAT,
    "openai-chat": OPENAI_CHAT,
    "chat-completions": OPENAI_CHAT,
    "anthropic": ANTHROPIC_MESSAGES,
    "anthropic-messages": ANTHROPIC_MESSAGES,
    "messages": ANTHROPIC_MESSAGES,
}
PARSERS = {OPENAI_CHAT: openai.parse, ANTHROPIC_MESSAGES: anthropic.parse}
LIST_KEYS = ("turns", "records", "exchanges", "entries", "rows")

__all__ = [
    "ANTHROPIC_MESSAGES",
    "OPENAI_CHAT",
    "FORMATS",
    "Cassette",
    "Exchange",
    "ImporterError",
    "load",
    "sniff",
]


def _jsonl(text, name):
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ImporterError(name + " 第 " + str(lineno) + " 行不是合法 JSON：" + str(exc)) from exc
    return rows


def read_rows(source):
    """读成 Python 对象列表；source 可以是路径，也可以已经是对象列表。"""
    if isinstance(source, (list, tuple)):
        return list(source), "<memory>"
    path = Path(source)
    if not path.exists():
        raise ImporterError("找不到日志文件：" + str(path))
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ImporterError("读不了日志文件 " + str(path) + "：" + str(exc)) from exc
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ImporterError(path.name + " 不是合法 JSON：" + str(exc)) from exc
        if not isinstance(data, list):
            raise ImporterError(path.name + " 顶层不是数组")
        return data, path.name
    if stripped.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return _jsonl(text, path.name), path.name
        if isinstance(data, list):
            return data, path.name
        if isinstance(data, dict):
            for key in LIST_KEYS:
                if isinstance(data.get(key), list):
                    return data[key], path.name
            return [data], path.name
        return [data], path.name
    return _jsonl(text, path.name), path.name


def _first_of(rows, key):
    for raw in rows:
        if isinstance(raw, dict) and isinstance(raw.get(key), list):
            return True
    return False


def sniff(rows, warnings):
    """判断是哪种风格；判不出来时按 openai-chat 处理并留下 warning。"""
    if _first_of(rows, "choices"):
        return OPENAI_CHAT
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        response = raw.get("response") if isinstance(raw.get("response"), dict) else raw
        if isinstance(response.get("choices"), list):
            return OPENAI_CHAT
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        request = raw.get("request") if isinstance(raw.get("request"), dict) else {}
        if isinstance(request.get("system"), (str, list)):
            return ANTHROPIC_MESSAGES
        response = raw.get("response") if isinstance(raw.get("response"), dict) else raw
        if isinstance(response.get("content"), list):
            return ANTHROPIC_MESSAGES
        if response.get("type") == "message" or "stop_reason" in response:
            return ANTHROPIC_MESSAGES
    warnings.add(
        "无法从内容判断日志风格，按 " + OPENAI_CHAT + " 处理；如果不是，请显式传 format="
    )
    return OPENAI_CHAT


def load(source, format=None, exit_code=None):
    """把一份日志读成 Cassette。

    source    日志文件路径，或已解析好的对象列表（测试用）。
    format    "openai-chat" / "anthropic-messages"，省略则自动判断。
    exit_code 日志里没有退出码时按 0 记录并在 warnings 里注明；这里可覆盖。
    """
    rows, name = read_rows(source)
    if not rows:
        raise ImporterError(name + " 里没有任何记录")
    warnings = Warnings()
    if format is None:
        fmt = sniff(rows, warnings)
    else:
        fmt = ALIASES.get(str(format).strip().lower())
        if fmt is None:
            raise ImporterError(
                "未知格式 " + repr(format) + "，v0.1 只支持：" + "、".join(FORMATS)
            )
    exchanges = PARSERS[fmt](rows, warnings)
    return build_cassette(exchanges, fmt=fmt, source=name, warnings=warnings, exit_code=exit_code)
