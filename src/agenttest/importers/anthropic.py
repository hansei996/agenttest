"""Anthropic Messages 风格的日志 -> Exchange。

一轮 = request（model / messages / system / tools）+ response（content blocks）。
assistant 的 tool_use 成为 tool.call，下一轮 user 消息里的 tool_result 成为
tool.result（配对同样是按 tool_use_id，由 _common 完成）。
"""

from __future__ import annotations

from ._common import Exchange

TEXT_BLOCKS = ("text",)


def tool_names(tools) -> list:
    names: list = []
    for item in tools or ():
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def _blocks(content, warnings, where):
    """把 content（字符串或 block 数组）拆成 (text, tool_calls, tool_results)。"""
    if content is None:
        return "", [], []
    if isinstance(content, str):
        return content, [], []
    if not isinstance(content, list):
        warnings.add(where + " 的 content 类型无法映射：" + type(content).__name__)
        return str(content), [], []
    parts: list = []
    calls: list = []
    results: list = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            warnings.add(where + " 里有无法映射的 content block：" + repr(block))
            continue
        kind = block.get("type")
        if kind in TEXT_BLOCKS or (kind is None and "text" in block):
            parts.append(str(block.get("text") or ""))
        elif kind == "tool_use":
            args = block.get("input")
            if args is None:
                args = {}
            elif not isinstance(args, dict):
                warnings.add(where + " 的 tool_use " + str(block.get("name")) + " 的 input 不是对象，原样保留")
                args = {"__raw_input__": args}
            calls.append({"id": block.get("id"), "name": str(block.get("name") or ""), "args": args})
        elif kind == "tool_result":
            body, _, _ = _blocks(block.get("content"), warnings, where + " 的 tool_result")
            results.append(
                {
                    "id": block.get("tool_use_id"),
                    "name": None,
                    "ok": not bool(block.get("is_error")),
                    "bytes": len(body.encode("utf-8")),
                }
            )
        else:
            warnings.add(where + " 里有无法映射的 content block 类型：" + str(kind))
    return "".join(parts), calls, results


def _message(message, warnings, where):
    if not isinstance(message, dict):
        warnings.add(where + " 里有无法映射的 message：" + repr(message))
        return None
    role = str(message.get("role") or "user")
    where = where + " 的 " + role + " 消息"
    text, calls, results = _blocks(message.get("content"), warnings, where)
    normalized = {"role": role, "content": text}
    if calls:
        normalized["tool_calls"] = calls
    if results:
        normalized["tool_results"] = results
    return normalized


def _usage(usage_raw, warnings, where):
    usage_raw = usage_raw if isinstance(usage_raw, dict) else {}
    cached = [
        key
        for key in ("cache_creation_input_tokens", "cache_read_input_tokens")
        if usage_raw.get(key)
    ]
    if cached:
        warnings.add(
            where + " 的 usage 里有 " + "、".join(cached) + "，计费口径不同未计入 usage.in"
        )
    return {
        "in": int(usage_raw.get("input_tokens") or 0),
        "out": int(usage_raw.get("output_tokens") or 0),
    }


def parse(rows, warnings) -> list:
    exchanges: list = []
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            warnings.add("第 " + str(index) + " 条记录不是 JSON 对象，已跳过")
            continue
        request = raw.get("request") if isinstance(raw.get("request"), dict) else {}
        response = raw.get("response")
        if response is None and isinstance(raw.get("content"), list):
            response = raw
        if not isinstance(response, dict):
            warnings.add("第 " + str(index) + " 条记录没有可识别的 response，已跳过")
            continue

        where = "第 " + str(index) + " 轮"
        messages = request.get("messages") or raw.get("messages") or []
        if not isinstance(messages, list):
            warnings.add(where + " 的 request.messages 不是数组，按空处理")
            messages = []
        context: list = []
        system = request.get("system", raw.get("system"))
        if system is not None:
            body, _, _ = _blocks(system, warnings, where + " 的 system")
            context.append({"role": "system", "content": body})
        context.extend(item for item in (_message(m, warnings, where) for m in messages) if item)

        text, calls, results = _blocks(response.get("content"), warnings, where + " 的 response")
        if results:
            warnings.add(
                where + " 的 response 里出现 tool_result block，按规范它应在下一条 user 消息里"
                "（已按内容记录）"
            )
        stamp = raw.get("timestamp", raw.get("created_at", response.get("created_at")))
        try:
            timestamp = float(stamp) if stamp is not None else None
        except (TypeError, ValueError):
            warnings.add(where + " 的 timestamp 不是数字，按缺失处理")
            timestamp = None

        exchanges.append(
            Exchange(
                context=context,
                model=str(request.get("model") or raw.get("model") or "unknown"),
                tools=tool_names(request.get("tools") or raw.get("tools")),
                text=text,
                tool_calls=calls,
                usage=_usage(response.get("usage") or raw.get("usage"), warnings, where),
                timestamp=timestamp,
            )
        )
    return exchanges
