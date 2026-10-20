"""diff：四类结构化差异。"""

from __future__ import annotations

import pytest

from agenttest import cassette as cas
from agenttest.diff import cost_breakdown, diff_runs, multiset_diff, order_change, quote_tokens


def test_diff_prints_all_four_categories(run, examples):
    proc = run("diff", str(examples / "good"), str(examples / "bad"))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for header in ("新增", "缺失", "顺序", "成本"):
        assert header in out, header


def test_diff_shows_the_missing_quote_error(examples):
    before = cas.read_cassette(examples / "good")
    after = cas.read_cassette(examples / "bad")
    out = diff_runs(before, after, "good", "bad")
    missing = [line for line in out.splitlines() if "缺失" in line]
    assert any("quote_error" in line for line in missing)
    assert any("read_file(logs/app.log)" in line for line in missing)


def test_diff_shows_the_extra_edit_and_the_reorder(examples):
    before = cas.read_cassette(examples / "good")
    after = cas.read_cassette(examples / "bad")
    out = diff_runs(before, after, "good", "bad")
    added = [line for line in out.splitlines() if line.startswith("  + 新增")]
    assert any("edit_file(src/auth.py)" in line for line in added)
    order = [line for line in out.splitlines() if line.startswith("  ~ 顺序")]
    assert order and "read_file(src/auth.py)" in order[0]


def test_diff_cost_line_reports_tokens(examples):
    before = cas.read_cassette(examples / "good")
    after = cas.read_cassette(examples / "bad")
    line = [l for l in diff_runs(before, after, "good", "bad").splitlines() if "成本" in l][0]
    assert "tokens" in line and "工具调用" in line


def test_identical_runs_have_no_differences(examples):
    events = cas.read_cassette(examples / "good")
    out = diff_runs(events, events, "a", "b")
    assert "（无）" in out
    assert "tokens 6,800 → 6,800" in out


def test_quote_tokens_are_extracted_from_model_output(examples):
    tokens = quote_tokens(cas.read_cassette(examples / "good"))
    assert "quote_error" in tokens
    assert "KeyError" in tokens


def test_multiset_diff_keeps_order():
    added, missing = multiset_diff(["a", "b", "c"], ["b", "c", "d"])
    assert added == ["d"]
    assert missing == ["a"]


def test_order_change_detects_a_swap():
    assert order_change(["x", "y"], ["y", "x"]) is not None
    assert order_change(["x", "y"], ["x", "y"]) is None


def test_cost_breakdown_counts_tool_calls(examples):
    cost = cost_breakdown(cas.read_cassette(examples / "good"))
    assert cost["tool_calls"] == 4
    assert cost["tokens"] > 0
