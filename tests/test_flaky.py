"""不稳定判定核心：判定分档、与 stat 的置信区间一致、样本不足不给结论。"""

from __future__ import annotations

import pytest

from agenttest import flaky as fk
from agenttest import stat as st


def test_all_pass_is_stable_pass():
    verdict = fk.classify(5, 5)
    assert verdict.value == fk.STABLE_PASS
    assert verdict.is_noisy is False
    assert verdict.pass_rate == 1.0


def test_all_fail_is_stable_fail():
    verdict = fk.classify(0, 5)
    assert verdict.value == fk.STABLE_FAIL
    assert verdict.is_noisy is False


def test_mixed_is_flaky_and_says_it_is_noise():
    verdict = fk.classify(3, 5)
    assert verdict.value == fk.FLAKY
    assert verdict.is_noisy is True
    low, high = st.wilson_interval(3, 5)
    assert verdict.low == low and verdict.high == high
    assert "把噪声当信号" in verdict.note
    assert "3/5" in verdict.note


def test_interval_always_comes_from_stat_module():
    for passed, runs in ((0, 5), (1, 5), (3, 5), (5, 5), (7, 20), (390, 400)):
        verdict = fk.classify(passed, runs)
        low, high = st.wilson_interval(passed, runs)
        assert (verdict.low, verdict.high) == (low, high)


def test_small_sample_is_unreliable_and_asks_for_more_runs():
    verdict = fk.classify(4, 4)
    assert verdict.value == fk.UNRELIABLE
    assert "样本不足" in verdict.note
    assert "再跑 1 次" in verdict.note
    assert fk.classify(0, 1).value == fk.UNRELIABLE


def test_unproven_edge_says_so_instead_of_claiming_99_percent():
    verdict = fk.classify(5, 5)
    assert verdict.value == fk.STABLE_PASS
    assert verdict.edge is True  # 5/5 的 Wilson 下界只有 0.57，够不到 0.99
    assert round(verdict.low, 4) == 0.5655
    assert "不是已验证的 99% 稳定" in verdict.note
    assert "n ≥ 381" in verdict.note


def test_strict_mode_gives_no_stable_verdict_without_the_bound():
    assert fk.classify(5, 5, edge=False).value == fk.FLAKY
    assert fk.classify(0, 5, edge=False).value == fk.FLAKY
    # bound 放宽到 0.5 时，5/5 靠区间本身就能站住
    relaxed = fk.classify(5, 5, bound=0.5)
    assert relaxed.value == fk.STABLE_PASS and relaxed.edge is False
    assert fk.classify(0, 5, bound=0.5).value == fk.STABLE_FAIL


def test_large_all_pass_sample_reaches_the_bound():
    verdict = fk.classify(381, 381)
    assert verdict.value == fk.STABLE_PASS
    assert verdict.edge is False
    assert verdict.low >= 0.99


def test_runs_needed_matches_the_arithmetic():
    assert fk.runs_needed(0.99) == 381
    assert fk.runs_needed(0.5) == 4  # Wilson(4,4) 下界 0.5100 ≥ 0.5


def test_min_runs_is_configurable():
    assert fk.classify(2, 2, min_runs=2).value == fk.STABLE_PASS
    assert fk.classify(2, 2, min_runs=3).value == fk.UNRELIABLE


def test_impossible_samples_are_rejected():
    with pytest.raises(fk.FlakyError):
        fk.classify(1, 0)
    with pytest.raises(fk.FlakyError):
        fk.classify(6, 5)
    with pytest.raises(fk.FlakyError):
        fk.classify(1, 5, bound=1.5)


def test_verdict_serializes_for_reports():
    data = fk.classify(3, 5).to_dict()
    assert data["verdict"] == fk.FLAKY
    assert data["noisy"] is True
    assert data["runs"] == 5 and data["passed"] == 3
    assert 0.0 <= data["low"] <= data["high"] <= 1.0
