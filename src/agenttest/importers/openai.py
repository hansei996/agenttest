"""OpenAI Chat Completions 风格的日志 -> Exchange。

一行（或数组里一个元素）是一轮：request 是发给模型的东西，response 是
completion。回执（role=tool）通常出现在**下一轮**的 request.messages 里，
所以这里只负责把一条消息规范化，配对交给 _common。
"""

from __future__ import annotations

import json

from ._common import Exchange


def tool_names(tools) -> list:
    names: list = []
    for item in tools or ():
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            function = item.get("function") if isinstance(item.get("function"), dict) else None
            if function and function.get("name"):
                names.append(str(function["name"]))
            elif item.get("name"):
                names.append(str(item["name"]))
    return names


def _text_of(content, warnings, where):
    """content 可能是字符串，也可能是 [{type:text,...}, ...]。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                warnings.add(where + " 里有无法映射的 content 片段：" + repr(block))
                continue
            kind = block.get("type")
            if kind in ("text", "input_text", "output_text") or (kind is None and "text" in block):
                parts.append(str(block.get("text") or ""))
            else:
                warnings.add(where + " 里有无法映射的 content 片段类型：" + str(kind))
        return "".join(parts)
    warnings.add(where + " 的 content 类型无法映射：" + type(content).__name__)
    return str(content)


def _tool_calls(message, warnings, where):
    calls: list = []
    for raw in message.get("tool_calls") or ():
        if not isinstance(raw, dict):
            warnings.add(where + " 里有无法映射的 tool_call：" + repr(raw))
            continue
        kind = raw.get("type")
        if kind not in (None, "function"):
            warnings.add(where + " 里有非 function 的 tool_call 类型：" + str(kind))
        function = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = function.get("name") or raw.get("name") or ""
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments.strip() else {}
            except ValueError:
                warnings.add(
                    where + " 的 tool_call " + str(name) + " 的 arguments 不是合法 JSON，原样保留"
                )
                args = {"__raw_arguments__": arguments}
        elif isinstance(arguments, dict):
            args = arguments
        elif arguments is None:
            args = {}
        else:
            warnings.add(where + " 的 tool_call " + str(name) + " 的 arguments 类型无法映射")
            args = {"__raw_arguments__": str(arguments)}
        if not isinstance(args, dict):
            args = {"__raw_arguments__": args}
        calls.append({"id": raw.get("id"), "name": str(name), "args": args})
    return calls


def _message(message, warnings, where):
    """把一条原始消息规范成 {"role","content","tool_calls"/"tool_results"}。"""
    if not isinstance(message, dict):
        warnings.add(where + " 里有无法映射的 message：" + repr(message))
        return None
    role = str(message.get("role") or "user")
    where = where + " 的 " + role + " 消息"
    if role == "tool":
        body = _text_of(message.get("content"), warnings, where)
        result = {
            "id": message.get("tool_call_id"),
            "name": message.get("name"),
            "ok": not bool(message.get("is_error")),
            "bytes": len(body.encode("utf-8")),
        }
        return {"role": "tool", "content": body, "tool_results": [result]}
    normalized = {"role": role, "content": _text_of(message.get("content"), warnings, where)}
    calls = _tool_calls(message, warnings, where)
    if calls:
        normalized["tool_calls"] = calls
    return normalized


def _normalize(raw):
    """一行原始记录 -> (request 头信息, response message, usage, timestamp)。"""
    request = raw.get("request") if isinstance(raw.get("request"), dict) else {}
    response = raw.get("response")
    if response is None and isinstance(raw.get("choices"), list):
        response = raw
    if response is None and isinstance(raw.get("message"), dict):
        response = {"choices": [{"message": raw["message"]}], "usage": raw.get("usage")}
    return request, response


def parse(rows, warnings) -> list:
    exchanges: list = []
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            warnings.add("第 " + str(index) + " 条记录不是 JSON 对象，已跳过")
            continue
        request, response = _normalize(raw)
        if not isinstance(response, dict):
            warnings.add("第 " + str(index) + " 条记录没有可识别的 response，已跳过")
            continue
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
        elif "role" in response or "content" in response:
            message = response
        else:
            message = None
        if not isinstance(message, dict):
            warnings.add("第 " + str(index) + " 条记录没有可识别的 assistant message，已跳过")
            continue

        where = "第 " + str(index) + " 轮"
        messages = request.get("messages") or raw.get("messages") or []
        if not isinstance(messages, list):
            warnings.add(where + " 的 request.messages 不是数组，按空处理")
            messages = []
        context = [item for item in (_message(m, warnings, where) for m in messages) if item]

        usage_raw = response.get("usage") or raw.get("usage") or {}
        usage = {
            "in": int(usage_raw.get("prompt_tokens", usage_raw.get("input_tokens", 0)) or 0),
            "out": int(usage_raw.get("completion_tokens", usage_raw.get("output_tokens", 0)) or 0),
        }
        stamp = raw.get("timestamp", raw.get("created", response.get("created")))
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
                text=_text_of(message.get("content"), warnings, where),
                tool_calls=_tool_calls(message, warnings, where),
                usage=usage,
                timestamp=timestamp,
            )
        )
    return exchanges
