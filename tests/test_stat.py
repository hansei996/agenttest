"""统计断言：record --repeat 采样、stat 判定、样本不足必须警告。"""

from __future__ import annotations

import json
import sys

import pytest

from agenttest import cassette as cas
from agenttest import stat as st


def batch_of(oks, tokens, durations, tools):
    return [
        {
            "run": index + 1,
            "ok": ok,
            "exit_code": 0 if ok else 1,
            "tokens": tokens[index],
            "duration": durations[index],
            "tool_calls": tools[index],
        }
        for index, ok in enumerate(oks)
    ]


def test_summarize_batch_math():
    stats = st.summarize_batch(
        batch_of([True, True, False], [100, 300, 200], [1.0, 3.0, 2.0], [2, 4, 3])
    )
    assert stats.runs == 3
    assert stats.successes == 2
    assert round(stats.success, 4) == round(2 / 3, 4)
    assert stats.mean_tokens == 200.0
    assert stats.mean_duration == 2.0
    assert stats.mean_tool_calls == 3.0
    assert stats.value("success") == stats.success


def test_parse_stat_assertion_forms():
    parsed = st.parse_stat_assertion("success>=0.8")
    assert (parsed.metric, parsed.op, parsed.threshold) == ("success", ">=", 0.8)
    parsed = st.parse_stat_assertion("tokens<=2000")
    assert (parsed.metric, parsed.op, parsed.threshold) == ("tokens", "<=", 2000.0)
    assert st.parse_stat_assertion("tools<=6").metric == "tool_calls"
    assert st.parse_stat_assertion("stat:duration<=5").metric == "duration"


def test_parse_stat_assertion_rejects_bad_input():
    with pytest.raises(st.StatError):
        st.parse_stat_assertion("cash>=0.8")
    with pytest.raises(st.StatError):
        st.parse_stat_assertion("success>=much")
    with pytest.raises(st.StatError):
        st.parse_stat_assertion("success")


def test_evaluate_stat_prints_measured_value():
    stats = st.summarize_batch(
        batch_of([True, True, False, True, False], [1000] * 5, [1.0] * 5, [3] * 5)
    )
    passed = st.evaluate_stat(st.parse_stat_assertion("success>=0.5"), stats)
    assert passed.ok is True
    assert "实测 0.60" in passed.message
    failed = st.evaluate_stat(st.parse_stat_assertion("tokens<=500"), stats)
    assert failed.ok is False
    assert "实测 1,000" in failed.message
    assert "超过阈值" in failed.message


def test_wilson_interval_is_honest_about_small_samples():
    low, high = st.wilson_interval(3, 3)
    assert low < 1.0 and high == 1.0
    low, high = st.wilson_interval(3, 5)
    assert 0.0 < low < 0.6 < high <= 1.0


def test_confidence_note_warns_below_min_sample():
    few = st.summarize_batch(batch_of([True, True, False], [1, 2, 3], [1, 1, 1], [1, 1, 1]))
    note = st.confidence_note(few)
    assert note is not None
    assert "WARN" in note and "置信区间" in note and "3 次" in note
    enough = st.summarize_batch(batch_of([True] * 5, [1] * 5, [1] * 5, [1] * 5))
    assert st.confidence_note(enough) is None


def test_batch_read_write_roundtrip(tmp_path):
    summaries = batch_of([True, False], [10, 20], [0.1, 0.2], [1, 2])
    path = st.write_batch(tmp_path / "batchdir", summaries)
    assert path.name == "batch.jsonl"
    assert st.read_batch(tmp_path / "batchdir") == summaries
    assert st.read_batch(path) == summaries


def test_read_batch_missing_file(tmp_path):
    with pytest.raises(st.StatError) as excinfo:
        st.read_batch(tmp_path / "nothing")
    assert "找不到 batch 文件" in str(excinfo.value)


def test_summarize_run_uses_assertions_for_success(examples):
    events = cas.read_cassette(examples / "good")
    ok = st.summarize_run(events, ["before:quote_error", "exit:0"], index=1)
    assert ok["ok"] is True
    assert ok["failures"] == []
    assert ok["tokens"] > 0 and ok["tool_calls"] == 4
    bad = st.summarize_run(events, ["before:no_such_error"], index=2)
    assert bad["ok"] is False
    assert "FAIL before:no_such_error" in bad["failures"][0]


def test_cli_record_repeat_and_stat_pass(run, tmp_path, repo):
    proc = run(
        "record",
        "--repeat",
        "5",
        str(tmp_path / "batch"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    assert proc.returncode == 0, proc.stderr
    batch = st.read_batch(tmp_path / "batch")
    assert len(batch) == 5
    assert all(item["ok"] for item in batch)
    assert (tmp_path / "batch" / "runs" / "run-1" / "cassette.jsonl").exists()

    verdict = run(
        "stat",
        str(tmp_path / "batch" / "batch.jsonl"),
        "--assert",
        "success>=0.8",
        "--assert",
        "tokens<=20000",
    )
    assert verdict.returncode == 0, verdict.stdout + verdict.stderr
    assert "实测 1.00" in verdict.stdout
    assert "PASS success>=0.8" in verdict.stdout


def test_cli_stat_fails_when_threshold_misses(run, tmp_path):
    proc = run(
        "record",
        "--repeat",
        "5",
        str(tmp_path / "batch"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "bad",
    )
    assert proc.returncode == 0, proc.stderr
    verdict = run("stat", str(tmp_path / "batch"), "--assert", "tokens<=10")
    assert verdict.returncode != 0
    assert "FAIL tokens<=10" in verdict.stdout
    assert "实测" in verdict.stdout


def test_cli_small_sample_is_warned(run, tmp_path):
    proc = run(
        "record",
        "--repeat",
        "3",
        str(tmp_path / "small"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    assert proc.returncode == 0, proc.stderr
    assert "WARN" in proc.stdout and "置信区间" in proc.stdout
    verdict = run("stat", str(tmp_path / "small"))
    assert verdict.returncode == 0
    assert "WARN" in verdict.stdout


def test_cli_stat_without_assertions_reports_measured_values(run, tmp_path):
    run(
        "record",
        "--repeat",
        "2",
        str(tmp_path / "b"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    verdict = run("stat", str(tmp_path / "b"))
    assert verdict.returncode == 0
    assert "成功" in verdict.stdout and "tokens" in verdict.stdout and "工具调用" in verdict.stdout


def test_cli_stat_rejects_broken_assertion(run, tmp_path):
    run(
        "record",
        "--repeat",
        "2",
        str(tmp_path / "b"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    verdict = run("stat", str(tmp_path / "b"), "--assert", "cash>=0.8")
    assert verdict.returncode != 0
    assert "未知统计量" in verdict.stderr
