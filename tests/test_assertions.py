"""断言语言：直白的失败信息 + 正确的退出码。"""

from __future__ import annotations

import pytest

from agenttest import assertions as asrt
from agenttest import cassette as cas


def good_events(examples):
    return cas.read_cassette(examples / "good")


def bad_events(examples):
    return cas.read_cassette(examples / "bad")


def test_good_behaviour_passes(run, examples):
    proc = run(
        "replay",
        str(examples / "good"),
        "--assert",
        "before:quote_error",
        "--assert",
        "touched:src/auth.py",
        "--assert",
        "exit:0",
        "--assert",
        "tool:read_file(path=logs/app.log)",
        "--assert",
        "never:tool=delete_file",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_bad_behaviour_fails_with_non_zero_exit(run, examples):
    proc = run("replay", str(examples / "bad"), "--assert", "before:quote_error")
    assert proc.returncode != 0
    assert "FAIL before:quote_error" in proc.stdout
    assert "第 4 个事件就是 edit_file(src/auth.py)" in proc.stdout


def test_before_failure_message_shape(examples):
    result = asrt.evaluate("before:quote_error", bad_events(examples))
    assert result.ok is False
    assert result.message.startswith("FAIL before:quote_error — 期望在第一次 edit 之前出现引用报错")
    assert "第 4 个事件就是 edit_file(src/auth.py)" in result.message


def test_before_passes_when_error_is_quoted_first(examples):
    assert asrt.evaluate("before:quote_error", good_events(examples)).ok is True


def test_touched_failure_lists_actual_files(examples):
    result = asrt.evaluate("touched:src/missing.py", good_events(examples))
    assert result.ok is False
    assert "src/missing.py" in result.message
    assert "src/auth.py" in result.message


def test_tool_assertion_reports_the_real_sequence(examples):
    result = asrt.evaluate("tool:read_file(path=logs/nope.log)", good_events(examples))
    assert result.ok is False
    assert "read_file(logs/app.log)" in result.message


def test_never_assertion_flags_the_event_index(examples):
    result = asrt.evaluate("never:tool=edit_file", good_events(examples))
    assert result.ok is False
    assert "edit_file(src/auth.py)" in result.message


def test_exit_assertion(examples):
    assert asrt.evaluate("exit:0", good_events(examples)).ok is True
    assert asrt.evaluate("exit:1", good_events(examples)).ok is False


def test_stat_is_explicitly_not_implemented(examples):
    result = asrt.evaluate("stat:success>=0.8,n=20", good_events(examples))
    assert result.ok is False
    assert "未实现统计断言" in result.message


def test_unknown_assertion_kind_is_a_usage_error(examples):
    with pytest.raises(asrt.AssertionError_):
        asrt.evaluate("bench:0", good_events(examples))


def test_broken_assertion_expression_exits_non_zero(run, examples):
    proc = run("replay", str(examples / "good"), "--assert", "before-nothing")
    assert proc.returncode != 0
