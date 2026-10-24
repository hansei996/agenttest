"""回归看板：混合 run 的汇总、基线比对、HTML、退出码策略、坏输入的人话错误。"""

from __future__ import annotations

import json
import shutil

import pytest
from pathlib import Path

from agenttest import regress as rg


def make_runs(root, mapping):
    """mapping: {run_id: 源 cassette 目录}"""
    for run_id, source in mapping.items():
        target = root / run_id
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "cassette.jsonl", target / "cassette.jsonl")
    return root


def mixed_runs(tmp_path, examples):
    return make_runs(tmp_path / "runs", {"good-run": examples / "good", "bad-run": examples / "bad"})


# -- ① 好/坏混合 ---------------------------------------------------------
def test_report_covers_every_run_and_assertion(tmp_path, examples):
    report = rg.regress(mixed_runs(tmp_path, examples), asserts=["before:quote_error"])
    assert [run.run_id for run in report.runs] == ["bad-run", "good-run"]
    by_id = {run.run_id: run for run in report.runs}
    assert by_id["good-run"].passed is True
    assert by_id["bad-run"].passed is False
    assert report.passed_runs == 1 and len(report.runs) == 2
    assert round(report.pass_rate, 2) == 0.5
    # 指标来自 cassette，不需要重放
    assert by_id["good-run"].tokens == 6800
    assert by_id["good-run"].tool_calls == 4


def test_failure_reuses_assertion_message_and_event_index(tmp_path, examples):
    report = rg.regress(mixed_runs(tmp_path, examples), asserts=["before:quote_error"])
    bad = {run.run_id: run for run in report.runs}["bad-run"]
    failure = bad.failures[0]
    assert failure.expr == "before:quote_error"
    assert failure.event_index == 4  # 第一次失败发生在第 4 个事件（assertions 的既有文案）
    assert "第 4 个事件就是 edit_file(src/auth.py)" in failure.message
    assert "FAIL before:quote_error" in failure.message


def test_terminal_table_shows_a_row_per_run(tmp_path, examples, run):
    proc = run("regress", str(mixed_runs(tmp_path, examples)), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stderr  # 没有基线时默认放行，见退出码策略
    assert "regress" in proc.stdout and "2 次运行" in proc.stdout
    assert "bad-run" in proc.stdout and "good-run" in proc.stdout
    assert "FAIL(第4事件)" in proc.stdout
    assert "通过率      1/2" in proc.stdout


# -- ② 基线比对 ---------------------------------------------------------
def test_baseline_detects_newly_failing(tmp_path, examples):
    baseline_dir = make_runs(tmp_path / "before", {"run-1": examples / "good"})
    baseline = rg.regress(baseline_dir, asserts=["before:quote_error"], out=tmp_path / "baseline.json")
    assert baseline.passed_runs == 1

    current_dir = make_runs(tmp_path / "after", {"run-1": examples / "bad"})
    current = rg.regress(current_dir, asserts=["before:quote_error"], baseline=tmp_path / "baseline.json")

    comparison = current.comparison
    assert len(comparison.newly_failing) == 1
    item = comparison.newly_failing[0]
    assert item["run_id"] == "run-1" and item["expr"] == "before:quote_error"
    assert item["event_index"] == 4
    assert comparison.fixed == []
    assert comparison.pass_rate_before == 1.0 and comparison.pass_rate_after == 0.0
    assert comparison.pass_rate_delta == -1.0


def test_baseline_detects_fixed(tmp_path, examples):
    baseline_dir = make_runs(tmp_path / "before", {"run-1": examples / "bad"})
    rg.regress(baseline_dir, asserts=["before:quote_error"], out=tmp_path / "baseline.json")
    current_dir = make_runs(tmp_path / "after", {"run-1": examples / "good"})
    current = rg.regress(current_dir, asserts=["before:quote_error"], baseline=tmp_path / "baseline.json")
    assert current.comparison.newly_failing == []
    assert current.comparison.fixed == [{"run_id": "run-1", "expr": "before:quote_error"}]
    assert current.comparison.pass_rate_delta == 1.0


def test_baseline_cost_delta_is_reported(tmp_path, examples):
    baseline_dir = make_runs(tmp_path / "before", {"run-1": examples / "good"})
    rg.regress(baseline_dir, asserts=[], out=tmp_path / "baseline.json")
    current_dir = make_runs(tmp_path / "after", {"run-1": examples / "bad"})
    current = rg.regress(current_dir, asserts=[], baseline=tmp_path / "baseline.json")
    tokens = current.comparison.cost["tokens"]
    assert tokens["before"] == 6800 and tokens["after"] == 5380
    assert tokens["delta"] == -1420


def test_cli_baseline_output_is_readable(run, tmp_path, examples):
    baseline_dir = make_runs(tmp_path / "before", {"run-1": examples / "good"})
    assert run("regress", str(baseline_dir), "--assert", "before:quote_error", "--out", str(tmp_path / "base.json")).returncode == 0
    current_dir = make_runs(tmp_path / "after", {"run-1": examples / "bad"})
    proc = run(
        "regress",
        str(current_dir),
        "--assert",
        "before:quote_error",
        "--baseline",
        str(tmp_path / "base.json"),
    )
    assert proc.returncode == 1  # 有新增失败 → 门禁拦住
    assert "基线比对" in proc.stdout
    assert "新增失败    1 条" in proc.stdout
    assert "第一次失败在第 4 个事件" in proc.stdout
    assert "通过率      100% → 0%（-100 个百分点）" in proc.stdout


# -- ③ HTML ------------------------------------------------------------
def test_html_report_is_single_file_and_shows_failures(run, tmp_path, examples):
    out = tmp_path / "report"
    proc = run(
        "regress",
        str(mixed_runs(tmp_path, examples)),
        "--assert",
        "before:quote_error",
        "--out",
        str(out),
        "--html",
    )
    assert proc.returncode == 0, proc.stderr
    html_path = out / "index.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "bad-run" in html and "good-run" in html
    assert "失败详情" in html
    assert "第 4 个事件" in html
    assert "edit_file(src/auth.py)" in html
    # 单文件、无外部依赖
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "cdn" not in html.lower()
    assert sorted(p.name for p in out.iterdir()) == ["index.html", "report.json"]


def test_html_includes_baseline_section(run, tmp_path, examples):
    baseline_dir = make_runs(tmp_path / "before", {"run-1": examples / "good"})
    run("regress", str(baseline_dir), "--assert", "before:quote_error", "--out", str(tmp_path / "base.json"))
    current_dir = make_runs(tmp_path / "after", {"run-1": examples / "bad"})
    out = tmp_path / "report"
    run(
        "regress",
        str(current_dir),
        "--assert",
        "before:quote_error",
        "--baseline",
        str(tmp_path / "base.json"),
        "--out",
        str(out),
        "--html",
    )
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "基线比对" in html
    assert "新增失败（退步）" in html
    assert "100% → 0%" in html


# -- ④ 退出码策略 -------------------------------------------------------
def test_fail_on_any_flags_the_mixed_batch(run, tmp_path, examples):
    proc = run("regress", str(mixed_runs(tmp_path, examples)), "--assert", "before:quote_error", "--fail-on", "any")
    assert proc.returncode == 1
    assert "门禁 fail-on=any → exit 1" in proc.stdout


def test_fail_on_never_always_exits_zero(run, tmp_path, examples):
    proc = run(
        "regress", str(mixed_runs(tmp_path, examples)), "--assert", "before:quote_error", "--fail-on", "never"
    )
    assert proc.returncode == 0
    assert "门禁 fail-on=never → exit 0" in proc.stdout


def test_fail_on_newly_failing_ignores_pre_existing_failures(run, tmp_path, examples):
    # 一进来就失败的 run，没有基线时不算"退步"
    proc = run("regress", str(mixed_runs(tmp_path, examples)), "--assert", "before:quote_error")
    assert proc.returncode == 0
    # 有基线、且这次新增失败 → 拦住
    baseline_dir = make_runs(tmp_path / "before", {"bad-run": examples / "good", "good-run": examples / "good"})
    run("regress", str(baseline_dir), "--assert", "before:quote_error", "--out", str(tmp_path / "base.json"))
    current = run(
        "regress",
        str(mixed_runs(tmp_path / "cur", examples)),
        "--assert",
        "before:quote_error",
        "--baseline",
        str(tmp_path / "base.json"),
    )
    assert current.returncode == 1


def test_all_runs_failing_exits_non_zero_even_without_baseline(run, tmp_path, examples):
    only_bad = make_runs(tmp_path / "runs", {"bad-run": examples / "bad"})
    proc = run("regress", str(only_bad), "--assert", "before:quote_error")
    assert proc.returncode == 1
    assert "所有 run 都失败" in proc.stdout


def test_resolve_exit_code_rejects_unknown_policy(tmp_path, examples):
    report = rg.regress(mixed_runs(tmp_path, examples), asserts=["before:quote_error"])
    with pytest.raises(rg.RegressError):
        rg.resolve_exit_code(report, "sometimes")


# -- ⑤ 坏输入 ----------------------------------------------------------
def test_empty_directory_gives_a_human_error(run, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = run("regress", str(empty))
    assert proc.returncode == 1
    assert "里没找到任何 cassette.jsonl" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_missing_path_gives_a_human_error(run, tmp_path):
    proc = run("regress", str(tmp_path / "nope"))
    assert proc.returncode == 1
    assert "路径不存在" in proc.stderr


def test_corrupt_cassette_is_reported_not_crashed(run, tmp_path):
    broken = tmp_path / "runs" / "broken"
    broken.mkdir(parents=True)
    (broken / "cassette.jsonl").write_bytes(b"this is not json\n")
    proc = run("regress", str(tmp_path / "runs"), "--assert", "before:quote_error")
    assert proc.returncode == 1
    assert "Traceback" not in proc.stdout + proc.stderr
    assert "ERROR" in proc.stdout and "broken" in proc.stdout
    assert "不是合法 JSON" in proc.stdout


def test_binary_cassette_is_reported_with_encoding_hint(run, tmp_path):
    run_dir = tmp_path / "runs" / "binary"
    run_dir.mkdir(parents=True)
    (run_dir / "cassette.jsonl").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    proc = run("regress", str(tmp_path / "runs"))
    assert proc.returncode == 1
    assert "二进制文件" in proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr


def test_bad_assertion_expression_is_a_usage_error(run, tmp_path, examples):
    proc = run("regress", str(mixed_runs(tmp_path, examples)), "--assert", "before-nothing")
    assert proc.returncode == 1
    assert "断言写法不对" in proc.stderr


def test_report_json_roundtrip(tmp_path, examples):
    report = rg.regress(mixed_runs(tmp_path, examples), asserts=["before:quote_error"], out=tmp_path / "r")
    data = json.loads((tmp_path / "r" / "report.json").read_text(encoding="utf-8"))
    assert data["summary"]["runs"] == 2 and data["summary"]["passed"] == 1
    assert data["asserts"] == ["before:quote_error"]
    reloaded = rg.load_report(tmp_path / "r" / "report.json")
    assert [run.run_id for run in reloaded.runs] == [run.run_id for run in report.runs]
    assert reloaded.pass_rate == report.pass_rate


# ---------- --flaky-report：噪声分栏 ----------

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _flaky_json(path, verdict):
    payload = {
        "schema_version": "0.1.0",
        "generated_at": "x",
        "min_runs": 5,
        "runs": 5,
        "unreliable": False,
        "asserts": [{"expr": "before:quote_error", "runs": 5, "passed": 3, "pass_rate": 0.6,
                     "low": 0.23, "high": 0.88, "verdict": verdict,
                     "noisy": verdict == "MIXED_OBSERVED", "note": "x"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _two_run_dirs(tmp_path):
    base = tmp_path / "base" / "run-1"
    base.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(EXAMPLES / "good", base)
    cur = tmp_path / "cur" / "run-1"
    cur.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(EXAMPLES / "bad", cur)
    return tmp_path / "base", tmp_path / "cur", tmp_path


def test_flaky_report_moves_known_noise_out_of_regressions(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    rg.regress(base_dir, asserts=["before:quote_error"], out=tmp / "b")
    flaky = _flaky_json(tmp / "flaky.json", "MIXED_OBSERVED")
    report = rg.regress(cur_dir, asserts=["before:quote_error"], baseline=tmp / "b" / "report.json", flaky_report=flaky)
    assert report.comparison.newly_failing == []
    assert len(report.comparison.newly_failing_noisy) == 1
    rendered = rg.render_comparison(report.comparison)
    rendered = rendered if isinstance(rendered, str) else chr(10).join(rendered)
    assert "噪声失败" in rendered


def test_insufficient_runs_is_not_treated_as_noise(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    rg.regress(base_dir, asserts=["before:quote_error"], out=tmp / "b")
    flaky = _flaky_json(tmp / "flaky.json", "INSUFFICIENT_RUNS")
    report = rg.regress(cur_dir, asserts=["before:quote_error"], baseline=tmp / "b" / "report.json", flaky_report=flaky)
    assert len(report.comparison.newly_failing) == 1
    assert report.comparison.newly_failing_noisy == []


def test_without_flaky_report_behaviour_is_unchanged(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    rg.regress(base_dir, asserts=["before:quote_error"], out=tmp / "b")
    report = rg.regress(cur_dir, asserts=["before:quote_error"], baseline=tmp / "b" / "report.json")
    assert len(report.comparison.newly_failing) == 1
    assert report.comparison.newly_failing_noisy == []


def test_bad_flaky_report_is_loud(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    rg.regress(base_dir, asserts=["before:quote_error"], out=tmp / "b")
    broken = tmp / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(rg.RegressError):
        rg.regress(cur_dir, asserts=["before:quote_error"], baseline=tmp / "b" / "report.json", flaky_report=broken)


# ---------- HTML 首屏：一句话结论 ----------

def test_html_headline_states_the_conclusion_not_the_tool_name(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    report = rg.regress(cur_dir, asserts=["before:quote_error"], out=tmp / "r", html=True)
    html = (tmp / "r" / "index.html").read_text(encoding="utf-8")
    assert "<h1>1 次运行里 1 次没通过 before:quote_error</h1>" in html
    assert "<h1>agenttest regress</h1>" not in html


def test_html_all_pass_headline_says_so(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    report = rg.regress(base_dir, asserts=["before:quote_error"], out=tmp / "r2", html=True)
    html = (tmp / "r2" / "index.html").read_text(encoding="utf-8")
    assert "<h1>1 次运行，全部通过</h1>" in html


def test_html_does_not_leak_absolute_root_path(tmp_path):
    base_dir, cur_dir, tmp = _two_run_dirs(tmp_path)
    report = rg.regress(cur_dir, asserts=["before:quote_error"], out=tmp / "r3", html=True)
    html = (tmp / "r3" / "index.html").read_text(encoding="utf-8")
    assert str(tmp).replace("\\", "/") not in html
    assert str(tmp) not in html
