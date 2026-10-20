"""importers：日志 -> cassette 的两条输入路径。

覆盖点：两种格式、合成时间戳标记、warning 收集、确定性、哈希链、坏输入。
"""

from __future__ import annotations

import json

import pytest

from agenttest.cassette import CassetteError, chain_head, read_cassette
from agenttest.importers import ImporterError, load

EXAMPLES = ("openai-sample.jsonl", "anthropic-sample.json")


def oa_turn(text, *, calls=None, created=None, usage=(10, 5), request_messages=None):
    """构造一行 OpenAI 风格的日志记录。"""
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            for cid, name, args in calls
        ]
    response = {"choices": [{"message": message}]}
    if usage is not None:
        response["usage"] = {"prompt_tokens": usage[0], "completion_tokens": usage[1]}
    if created is not None:
        response["created"] = created
    return {
        "request": {"model": "gpt-test", "messages": request_messages or [{"role": "user", "content": text}]},
        "response": response,
    }


def oa_tool_message(call_id, name, content):
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}


def an_turn(text, *, calls=None, blocks=None, usage=(10, 5), timestamp=None, messages=None):
    """构造一轮 Anthropic 风格的日志记录。"""
    content = [{"type": "text", "text": text}]
    for index, (name, args) in enumerate(calls or []):
        content.append({"type": "tool_use", "id": "toolu_" + str(index + 1), "name": name, "input": args})
    content.extend(blocks or [])
    response = {
        "type": "message",
        "role": "assistant",
        "content": content,
        "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
    }
    if timestamp is not None:
        response["created_at"] = timestamp
    return {
        "request": {"model": "claude-test", "messages": messages or [{"role": "user", "content": text}]},
        "response": response,
    }


# -- 示例文件 ------------------------------------------------------------


def test_example_files_import_into_all_six_event_types(examples):
    for name in EXAMPLES:
        cassette = load(examples / "import" / name)
        assert set(cassette.counts) == {
            "run.start",
            "model.call",
            "model.result",
            "tool.call",
            "tool.result",
            "run.end",
        }, name
        assert cassette.counts["model.call"] == cassette.counts["model.result"] == 5
        assert cassette.counts["tool.call"] == cassette.counts["tool.result"] == 4


def test_example_files_round_trip_through_the_hash_chain(examples, tmp_path):
    for index, name in enumerate(EXAMPLES):
        cassette = load(examples / "import" / name)
        path = cassette.write(tmp_path / ("out" + str(index)))
        assert path.name == "cassette.jsonl"
        events = read_cassette(path)  # verify=True 默认开
        assert events == cassette.events
        assert chain_head(path) == json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["hash"]


def test_openai_sample_keeps_real_created_timestamps(examples):
    cassette = load(examples / "import" / "openai-sample.jsonl")
    assert cassette.synthetic_timestamps is False
    stamps = [event["t"] for event in cassette.events]
    assert stamps[0] == 0.0
    assert stamps == sorted(stamps)
    assert stamps[-1] == 1.9


def test_anthropic_sample_marks_synthetic_timestamps(examples):
    cassette = load(examples / "import" / "anthropic-sample.json")
    assert cassette.synthetic_timestamps is True
    stamps = [event["t"] for event in cassette.events]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps), "合成的 t 必须严格递增"
    assert any("synthetic timestamps" in item for item in cassette.warnings)


# -- 映射正确性 ----------------------------------------------------------


def test_openai_tool_calls_are_parsed_from_json_arguments():
    rows = [
        oa_turn("先读日志。", calls=[("call_1", "read_file", {"path": "logs/app.log"})]),
        oa_turn(
            "读文件。",
            calls=[("call_2", "edit_file", {"path": "src/auth.py"})],
            request_messages=[{"role": "tool", "tool_call_id": "call_1", "content": "boom"}],
        ),
    ]
    cassette = load(rows)
    results = [event for event in cassette.events if event["type"] == "model.result"]
    assert results[0]["tool_calls"] == [{"name": "read_file", "args": {"path": "logs/app.log"}}]
    calls = [event for event in cassette.events if event["type"] == "tool.call"]
    assert [call["name"] for call in calls] == ["read_file", "edit_file"]


def test_anthropic_tool_use_becomes_tool_call_and_tool_result_pairs():
    rows = [
        an_turn("先读日志。", calls=[("read_file", {"path": "logs/app.log"})]),
        an_turn(
            "读完了。",
            messages=[
                {"role": "user", "content": "log"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": [{"type": "text", "text": "boom"}],
                        }
                    ],
                },
            ],
        ),
    ]
    cassette = load(rows, format="anthropic-messages")
    results = [event for event in cassette.events if event["type"] == "tool.result"]
    assert len(results) == 1
    assert results[0] == {"name": "read_file", "ok": True, "bytes": 4, "t": results[0]["t"], "type": "tool.result"}
    calls = [event for event in cassette.events if event["type"] == "tool.call"]
    assert calls[0]["args"] == {"path": "logs/app.log"}


def test_anthropic_tool_result_is_error_flips_ok():
    rows = [
        an_turn("跑测试。", calls=[("run_tests", {"target": "t"})]),
        an_turn(
            "失败了。",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "is_error": True,
                            "content": [{"type": "text", "text": "1 failed"}],
                        }
                    ],
                }
            ],
        ),
    ]
    cassette = load(rows, format="anthropic-messages")
    results = [event for event in cassette.events if event["type"] == "tool.result"]
    assert results[0]["ok"] is False


def test_usage_maps_to_in_out():
    cassette = load([oa_turn("hi", usage=(1200, 300))])
    result = [event for event in cassette.events if event["type"] == "model.result"][0]
    assert result["usage"] == {"in": 1200, "out": 300}


# -- 时间戳策略 ----------------------------------------------------------


def test_missing_timestamp_on_any_turn_forces_all_synthetic():
    rows = [oa_turn("一", created=100.0), oa_turn("二")]
    cassette = load(rows)
    assert cassette.synthetic_timestamps is True
    stamps = [event["t"] for event in cassette.events]
    assert stamps == [round(index * 0.1, 4) for index in range(len(stamps))]


def test_real_timestamps_are_relative_to_the_first_turn():
    rows = [oa_turn("一", created=100.0), oa_turn("二", created=102.5)]
    cassette = load(rows)
    assert cassette.synthetic_timestamps is False
    model_calls = [event for event in cassette.events if event["type"] == "model.call"]
    assert [event["t"] for event in model_calls] == [0.0, 2.5]


def test_synthetic_marker_is_verifiable_in_the_written_cassette(tmp_path):
    cassette = load([an_turn("hi")])
    path = cassette.write(tmp_path)
    start = read_cassette(path)[0]
    assert start["type"] == "run.start"
    assert start["meta"]["synthetic_timestamps"] is True
    assert start["meta"]["warnings"] == cassette.warnings
    assert start["meta"]["format"] == "anthropic-messages"


# -- warning 收集 --------------------------------------------------------


def test_unmappable_anthropic_block_becomes_a_warning():
    rows = [an_turn("看图", blocks=[{"type": "image", "source": {"data": "..."}}])]
    cassette = load(rows, format="anthropic-messages")
    assert any("image" in item for item in cassette.warnings)
    assert any("无法映射" in item for item in cassette.warnings)


def test_unmappable_block_inside_request_message_warns_too():
    rows = [
        an_turn(
            "hi",
            messages=[
                {"role": "user", "content": [{"type": "image", "source": {}}, {"type": "text", "text": "看"}]}
            ],
        )
    ]
    cassette = load(rows, format="anthropic-messages")
    assert any("image" in item for item in cassette.warnings)


def test_openai_non_json_arguments_are_kept_raw_with_a_warning():
    rows = [
        {
            "request": {"model": "m", "messages": []},
            "response": {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{oops"}}
                            ],
                        }
                    }
                ]
            },
        }
    ]
    cassette = load(rows, format="openai-chat")
    calls = [event for event in cassette.events if event["type"] == "tool.call"]
    assert calls[0]["args"] == {"__raw_arguments__": "{oops"}
    assert any("不是合法 JSON" in item for item in cassette.warnings)


def test_tool_call_without_result_is_reported():
    cassette = load([oa_turn("只有请求", calls=[("c1", "read_file", {"path": "a"})])])
    assert any("没有对应的 tool_result" in item for item in cassette.warnings)
    assert cassette.counts["tool.call"] == 1
    assert cassette.counts.get("tool.result", 0) == 0


def test_orphan_tool_result_is_reported():
    rows = [
        oa_turn("一", request_messages=[{"role": "tool", "tool_call_id": "ghost", "content": "x"}]),
    ]
    cassette = load(rows)
    assert any("找不到对应的 tool_call" in item for item in cassette.warnings)


def test_exit_code_default_warning_and_override():
    default = load([oa_turn("hi")])
    assert any("exit_code" in item for item in default.warnings)
    explicit = load([oa_turn("hi")], exit_code=1)
    assert not any("exit_code" in item for item in explicit.warnings)
    end = [event for event in explicit.events if event["type"] == "run.end"][0]
    assert end["exit_code"] == 1


# -- 确定性 --------------------------------------------------------------


def test_two_loads_produce_identical_bytes(tmp_path):
    rows = [oa_turn("一", calls=[("c1", "read_file", {"path": "a"})], created=7.0)]
    first = load(rows).write(tmp_path / "first")
    second = load(rows).write(tmp_path / "second")
    assert first.read_bytes() == second.read_bytes()


# -- 坏输入 --------------------------------------------------------------


def test_unknown_format_string_is_rejected():
    with pytest.raises(ImporterError) as excinfo:
        load([oa_turn("hi")], format="openai-responses")
    assert "openai-responses" in str(excinfo.value)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ImporterError):
        load(tmp_path / "nope.jsonl")


def test_bad_jsonl_line_reports_its_line_number(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text("{}\n{not json}\n", encoding="utf-8")
    with pytest.raises(ImporterError) as excinfo:
        load(path)
    assert "第 2 行" in str(excinfo.value)


def test_empty_input_is_rejected(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ImporterError):
        load(path)


def test_json_array_and_jsonl_are_both_accepted(tmp_path):
    rows = [oa_turn("一", created=1.0), oa_turn("二", created=2.0)]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    as_json = tmp_path / "a" / "log.json"
    as_json.write_text(json.dumps(rows), encoding="utf-8")
    as_jsonl = tmp_path / "b" / "log.jsonl"
    as_jsonl.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    from_json = load(as_json)
    from_jsonl = load(as_jsonl)
    assert from_json.events[1:] == from_jsonl.events[1:]
    assert from_json.events[0]["meta"]["source"] == "log.json"
    assert from_jsonl.events[0]["meta"]["source"] == "log.jsonl"


def test_tampering_with_a_written_cassette_is_detected(tmp_path):
    path = load([oa_turn("hi", created=1.0)]).write(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"model":"gpt-test"', '"model":"other"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CassetteError):
        read_cassette(path)
