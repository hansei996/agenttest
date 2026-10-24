"""plan：样本量规划的回归测试（数字必须与 flaky.runs_needed 一致）。"""
from __future__ import annotations

import pytest

from agenttest import plan as pl
from agenttest.flaky import runs_needed, wilson_interval


def test_plan_matches_runs_needed_for_common_bounds():
    for bound in pl.COMMON_BOUNDS:
        row = pl.plan(bound)
        assert row["runs"] == runs_needed(bound)
        low, _ = wilson_interval(row["runs"], row["runs"])
        assert low >= bound - 1e-9, (bound, low)


def test_plan_known_values():
    assert pl.plan(0.5)["runs"] == 4
    assert pl.plan(0.9)["runs"] == 35
    assert pl.plan(0.99)["runs"] == 381


def test_plan_rejects_impossible_bounds():
    for bad in (0, 1, -0.1, 1.5):
        with pytest.raises(pl.PlanError):
            pl.plan(bad)


def test_table_covers_the_common_bounds_in_order():
    rows = pl.table()
    assert [r["bound"] for r in rows] == list(pl.COMMON_BOUNDS)
    runs = [r["runs"] for r in rows]
    assert runs == sorted(runs)
