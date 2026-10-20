"""replay 引擎：确定性、耗尽即失败、行为漂移可定位。"""

from __future__ import annotations

import pytest

from agenttest import cassette as cas
from agenttest import events as ev
from agenttest.replay import ReplayError, replay


def good_events(examples):
    return cas.read_cassette(examples / "good")


def test_replay_is_byte_for_byte_deterministic(run, examples):
    first = run("replay", str(examples / "good"), "--assert", "before:quote_error")
    second = run("replay", str(examples / "good"), "--assert", "before:quote_error")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout


def test_replay_reproduces_exactly_the_recorded_events(examples):
    outcome = replay(examples / "good")
    assert len(outcome.events) == len(outcome.recorded)
    for index, (want, got) in enumerate(zip(outcome.recorded, outcome.events)):
        assert ev.strip_volatile(want) == ev.strip_volatile(got), "第 " + str(index + 1) + " 个事件不一致"


def test_consumed_model_results_are_all_used(examples):
    outcome = replay(examples / "good")
    assert len(ev.model_results(outcome.recorded)) == len(ev.model_results(outcome.events))


def test_exhausted_model_results_fail_loudly(tmp_path, examples, run):
    events = good_events(examples)
    last_result = max(i for i, e in enumerate(events) if e["type"] == "model.result")
    trimmed = [e for i, e in enumerate(events) if i != last_result]
    target = tmp_path / "exhausted"
    cas.write_cassette(target, trimmed)
    proc = run("replay", str(target))
    assert proc.returncode != 0
    assert "model.result 耗尽" in proc.stderr
    assert "已消费" in proc.stderr


def test_behaviour_drift_is_reported_with_event_index(tmp_path, examples):
    events = good_events(examples)
    for event in events:
        if event["type"] == "tool.result":
            event["bytes"] = event["bytes"] + 1
            break
    target = tmp_path / "drift"
    cas.write_cassette(target, events)
    with pytest.raises(ReplayError) as excinfo:
        replay(target)
    message = str(excinfo.value)
    assert "行为漂移" in message
    assert "个事件" in message
