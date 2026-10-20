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
    # 确定性量照旧按实测值判定
    passed = st.evaluate_stat(st.parse_stat_assertion("tokens<=1000"), stats)
    assert passed.ok is True
    assert "实测 1,000" in passed.message
    failed = st.evaluate_stat(st.parse_stat_assertion("tokens<=500"), stats)
    assert failed.ok is False
    assert "实测 1,000" in failed.message
    assert "超过阈值" in failed.message
    # 比例量给的是点估计 + 置信区间，不是"实测"
    proportion = st.evaluate_stat(st.parse_stat_assertion("success>=0.5"), stats)
    assert proportion.ok is False  # 点估计 0.60 够，95% 下界 0.23 不够
    assert "点估计 0.60（3/5）" in proportion.message


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
        "success>=0.5",  # n=5 全成功时 95% 下界 0.57，只有 <=0.57 的阈值才默认成立
        "--assert",
        "tokens<=20000",
    )
    assert verdict.returncode == 0, verdict.stdout + verdict.stderr
    assert "点估计 1.00（5/5）" in verdict.stdout
    assert "PASS success>=0.5" in verdict.stdout
    assert "实测 20,000" not in verdict.stdout


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


def three_of_three():
    return st.summarize_batch(batch_of([True] * 3, [100] * 3, [0.5] * 3, [4] * 3))


def five_of_five():
    return st.summarize_batch(batch_of([True] * 5, [100] * 5, [0.5] * 5, [4] * 5))


def test_proportion_needs_the_ci_bound_not_the_point_estimate():
    result = st.evaluate_stat(st.parse_stat_assertion("success>=0.99"), three_of_three())
    assert result.ok is False
    assert "点估计 1.00（3/3）" in result.message
    assert "95% 置信区间 0.44–1.00" in result.message
    assert "下界 0.44" in result.message
    assert "样本不足，无法证明该阈值" in result.message


def test_point_estimate_escape_hatch_is_marked_as_not_significant():
    result = st.evaluate_stat(
        st.parse_stat_assertion("success>=0.99"), three_of_three(), point_estimate=True
    )
    assert result.ok is True
    assert "按点估计通过，非统计显著" in result.message
    assert "点估计 1.00（3/3）" in result.message


def test_five_successes_still_cannot_prove_point_eight():
    # Wilson(5,5) 的下界是 0.566：0.57 都还差一点，0.8 更不可能
    stats = five_of_five()
    assert st.evaluate_stat(st.parse_stat_assertion("success>=0.8"), stats).ok is False
    assert st.evaluate_stat(st.parse_stat_assertion("success>=0.57"), stats).ok is False
    passing = st.evaluate_stat(st.parse_stat_assertion("success>=0.56"), stats)
    assert passing.ok is True
    assert "下界 0.57" in passing.message


def test_proportion_point_estimate_also_flags_a_real_miss():
    stats = st.summarize_batch(batch_of([True, False, False], [1, 1, 1], [1, 1, 1], [1, 1, 1]))
    result = st.evaluate_stat(
        st.parse_stat_assertion("success>=0.9"), stats, point_estimate=True
    )
    assert result.ok is False
    assert "点估计 0.33（1/3）" in result.message


def test_numeric_metrics_ignore_the_confidence_interval():
    stats = three_of_three()
    assert st.evaluate_stat(st.parse_stat_assertion("tokens<=20000"), stats).ok is True
    assert st.evaluate_stat(st.parse_stat_assertion("tools<=4"), stats).ok is True
    assert st.evaluate_stat(st.parse_stat_assertion("tools<=3"), stats).ok is False


def test_report_flags_all_zero_durations():
    stats = st.summarize_batch(batch_of([True] * 5, [10] * 5, [0.0] * 5, [1] * 5))
    report = st.format_report("b.jsonl", stats, [])
    assert "所有运行的 duration 都是 0.000s" in report


def test_report_warns_when_point_estimate_is_used():
    report = st.format_report("b.jsonl", five_of_five(), [], point_estimate=True)
    assert "--point-estimate" in report and "不是统计显著" in report


def test_cli_small_sample_cannot_prove_a_high_threshold(run, tmp_path):
    proc = run(
        "record",
        "--repeat",
        "3",
        str(tmp_path / "three"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    assert proc.returncode == 0, proc.stderr
    verdict = run("stat", str(tmp_path / "three"), "--assert", "success>=0.99")
    assert verdict.returncode == 1
    assert "样本不足，无法证明该阈值" in verdict.stdout
    assert "FAIL success>=0.99" in verdict.stdout


def test_cli_point_estimate_flag_allows_exit_zero(run, tmp_path):
    run(
        "record",
        "--repeat",
        "3",
        str(tmp_path / "three"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    verdict = run(
        "stat", str(tmp_path / "three"), "--assert", "success>=0.99", "--point-estimate"
    )
    assert verdict.returncode == 0, verdict.stdout + verdict.stderr
    assert "非统计显著" in verdict.stdout


def test_cli_five_runs_cannot_prove_point_eight(run, tmp_path):
    run(
        "record",
        "--repeat",
        "5",
        str(tmp_path / "five"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "good",
    )
    verdict = run("stat", str(tmp_path / "five"), "--assert", "success>=0.8")
    assert verdict.returncode == 1
    assert "下界 0.57" in verdict.stdout

