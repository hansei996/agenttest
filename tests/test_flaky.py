"""抖动判定：证据式分档、与 stat 区间一致、CLI 表格与 --out JSON、坏输入人话错误。"""

from __future__ import annotations

import json
import shutil

import pytest

from agenttest import flaky as fk
from agenttest import stat as st


# -- 纯判定 -------------------------------------------------------------
def test_all_pass_is_passed_in_all_runs_and_says_the_bound_is_missing():
    verdict = fk.classify(5, 5)
    assert verdict.value == fk.PASSED_IN_ALL_RUNS
    assert verdict.is_noisy is False
    assert "区间下界 0.57 < 0.99" in verdict.note  # 5/5 的 Wilson 下界只有 0.57
    assert "n ≥ 381" in verdict.note


def test_all_fail_is_failed_in_all_runs_and_counts_passed_not_runs():
    verdict = fk.classify(0, 5)
    assert verdict.value == fk.FAILED_IN_ALL_RUNS
    assert verdict.is_noisy is False
    assert "0/5" in verdict.note  # 曾经错写成 5/5
    assert "5/5" not in verdict.note
    assert "区间上界 0.43 > 0.01" in verdict.note  # 曾经拿 0.99 去比，句子恒真


def test_mixed_is_mixed_observed_and_names_the_noise_risk():
    verdict = fk.classify(3, 5)
    assert verdict.value == fk.MIXED_OBSERVED
    assert verdict.is_noisy is True
    assert fk.NOISE_HINT in verdict.note
    assert "3/5" in verdict.note
    low, high = st.wilson_interval(3, 5)
    assert (verdict.low, verdict.high) == (low, high)


def test_sample_below_min_runs_is_insufficient():
    verdict = fk.classify(4, 4)
    assert verdict.value == fk.INSUFFICIENT_RUNS
    assert "样本不足" in verdict.note
    assert "再跑 1 次" in verdict.note
    assert fk.classify(0, 1).value == fk.INSUFFICIENT_RUNS


def test_legacy_names_are_aliases_only():
    assert fk.STABLE_PASS == fk.PASSED_IN_ALL_RUNS
    assert fk.STABLE_FAIL == fk.FAILED_IN_ALL_RUNS
    assert fk.FLAKY == fk.MIXED_OBSERVED
    assert fk.UNRELIABLE == fk.INSUFFICIENT_RUNS
    assert fk.classify(5, 5).to_dict()["legacy"] == "STABLE_PASS"
    assert fk.classify(3, 5).to_dict()["legacy"] == "FLAKY"


def test_interval_always_comes_from_stat_module():
    for passed, runs in ((0, 5), (1, 5), (3, 5), (5, 5), (20, 20), (390, 400)):
        verdict = fk.classify(passed, runs)
        assert (verdict.low, verdict.high) == st.wilson_interval(passed, runs)


def test_bound_path_and_strict_mode():
    relaxed = fk.classify(5, 5, bound=0.5)
    assert relaxed.value == fk.PASSED_IN_ALL_RUNS and relaxed.edge is False
    assert fk.classify(0, 5, bound=0.5).value == fk.FAILED_IN_ALL_RUNS
    assert fk.classify(5, 5, edge=False).value == fk.MIXED_OBSERVED
    assert fk.classify(381, 381).edge is False


def test_runs_needed_matches_the_arithmetic():
    assert fk.runs_needed(0.99) == 381
    assert fk.runs_needed(0.5) == 4


def test_impossible_samples_are_rejected():
    for args in ((1, 0), (6, 5)):
        with pytest.raises(fk.FlakyError):
            fk.classify(*args)
    with pytest.raises(fk.FlakyError):
        fk.classify(1, 5, bound=1.5)


def test_verdict_serializes_with_legacy_and_fail_rate_upper():
    data = fk.classify(5, 5).to_dict()
    assert data["verdict"] == fk.PASSED_IN_ALL_RUNS
    assert data["legacy"] == "STABLE_PASS"
    assert data["noisy"] is False
    assert data["fail_rate_upper"] == round(1 - st.wilson_interval(5, 5)[0], 4)


# -- CLI ---------------------------------------------------------------
def make_runs(root, good, bad, examples):
    """good 份 examples/good + bad 份 examples/bad，每个 run 一个目录。"""
    root.mkdir(parents=True, exist_ok=True)
    for index in range(good):
        target = root / ("run-g" + str(index))
        target.mkdir()
        shutil.copyfile(examples / "good" / "cassette.jsonl", target / "cassette.jsonl")
    for index in range(bad):
        target = root / ("run-b" + str(index))
        target.mkdir()
        shutil.copyfile(examples / "bad" / "cassette.jsonl", target / "cassette.jsonl")
    return root


def test_cli_five_of_five(run, tmp_path, examples):
    runs = make_runs(tmp_path / "five", 5, 0, examples)
    proc = run("flaky", str(runs), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stderr
    assert "PASSED_IN_ALL_RUNS" in proc.stdout
    assert "0.57–1.00" in proc.stdout
    assert "本表 n=5；5 次全过只排除失败率 > 43%，要到 ≤1% 需 381 次" in proc.stdout
    for legacy in ("STABLE_PASS", "STABLE_FAIL", "FLAKY", "UNRELIABLE"):
        assert legacy not in proc.stdout


def test_cli_zero_of_five(run, tmp_path, examples):
    runs = make_runs(tmp_path / "allbad", 0, 5, examples)
    proc = run("flaky", str(runs), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stderr
    assert "FAILED_IN_ALL_RUNS" in proc.stdout
    assert "0/5" in proc.stdout or "0.00–0.43" in proc.stdout
    assert "5/5 全败" not in proc.stdout


def test_cli_three_of_five_is_mixed_and_marked_as_noise(run, tmp_path, examples):
    runs = make_runs(tmp_path / "mixed", 3, 2, examples)
    proc = run("flaky", str(runs), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stderr  # 默认 --fail-on never
    assert "MIXED_OBSERVED" in proc.stdout
    assert fk.NOISE_HINT in proc.stdout
    assert "60%" in proc.stdout  # 3/5


def test_cli_fail_on_flaky_gates_and_never_does_not(run, tmp_path, examples):
    runs = make_runs(tmp_path / "mixed", 3, 2, examples)
    gate = run("flaky", str(runs), "--assert", "before:quote_error", "--fail-on", "flaky")
    assert gate.returncode == 1
    assert "exit 1" in gate.stdout
    calm = run("flaky", str(runs), "--assert", "before:quote_error", "--fail-on", "never")
    assert calm.returncode == 0


def test_cli_small_sample_marks_the_whole_table(run, tmp_path, examples):
    runs = make_runs(tmp_path / "small", 2, 0, examples)
    proc = run("flaky", str(runs), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stderr
    assert "INSUFFICIENT_RUNS" in proc.stdout
    assert "整表" in proc.stdout and "--min-runs 5" in proc.stdout
    assert "PASSED_IN_ALL_RUNS" not in proc.stdout  # 样本不足时不给结论
    relaxed = run("flaky", str(runs), "--assert", "before:quote_error", "--min-runs", "2")
    assert "PASSED_IN_ALL_RUNS" in relaxed.stdout


def test_cli_writes_json_report(run, tmp_path, examples):
    runs = make_runs(tmp_path / "five", 5, 0, examples)
    out = tmp_path / "report.json"
    proc = run("flaky", str(runs), "--assert", "before:quote_error", "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "0.1.0"
    assert data["generated_at"].endswith("Z")
    assert data["runs"] == 5 and data["min_runs"] == 5 and data["unreliable"] is False
    entry = data["asserts"][0]
    assert entry["expr"] == "before:quote_error"
    for key in ("runs", "passed", "pass_rate", "low", "high", "verdict", "legacy", "noisy", "note"):
        assert key in entry
    assert entry["verdict"] == fk.PASSED_IN_ALL_RUNS
    assert entry["runs"] == 5 and entry["passed"] == 5 and entry["pass_rate"] == 1.0
    assert entry["low"] == round(st.wilson_interval(5, 5)[0], 4)


def test_cli_empty_directory_is_a_human_error(run, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = run("flaky", str(empty), "--assert", "before:quote_error")
    assert proc.returncode == 1
    assert "里没找到任何 cassette.jsonl" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_corrupt_cassette_is_a_human_error(run, tmp_path):
    broken = tmp_path / "runs" / "broken"
    broken.mkdir(parents=True)
    (broken / "cassette.jsonl").write_bytes(b"not json at all\n")
    proc = run("flaky", str(tmp_path / "runs"), "--assert", "before:quote_error")
    assert proc.returncode == 1
    assert "cassette 读不了" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_bad_assertion_is_a_human_error(run, tmp_path, examples):
    runs = make_runs(tmp_path / "five", 5, 0, examples)
    proc = run("flaky", str(runs), "--assert", "before-nothing")
    assert proc.returncode == 1
    assert "断言写法不对" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_requires_at_least_one_assertion(run, tmp_path, examples):
    runs = make_runs(tmp_path / "five", 5, 0, examples)
    proc = run("flaky", str(runs))
    assert proc.returncode == 1
    assert "至少要一条 --assert" in proc.stderr


def test_collect_merges_multiple_directories(run, tmp_path, examples):
    first = make_runs(tmp_path / "a", 3, 0, examples)
    second = make_runs(tmp_path / "b", 0, 2, examples)
    proc = run("flaky", str(first), str(second), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stderr
    assert "5 次运行" in proc.stdout
    assert "MIXED_OBSERVED" in proc.stdout  # 3/5
