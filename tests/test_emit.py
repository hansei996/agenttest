"""emit：生产端 SDK 的回归测试（别人不装我们的 runner 也要能写合规 cassette）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agenttest import emit
from agenttest.cassette import read_cassette


def _basic_run():
    run = emit.Run(agent="demo-agent", argv=["python", "agent.py"])
    run.model_call([{"role": "user", "content": "fix it"}], tools=["read_file"])
    run.model_result("先看日志", tool_calls=[{"name": "read_file", "args": {"path": "logs/app.log"}}])
    run.tool_call("read_file", {"path": "logs/app.log"})
    run.tool_result("read_file", ok=True, bytes=66)
    run.end(exit_code=0, files={"src/auth.py": None})
    return run


def test_emit_writes_a_hash_chained_cassette(tmp_path):
    path = _basic_run().write(tmp_path / "demo")
    events = read_cassette(path)  # verify=True
    types = [e["type"] for e in events]
    assert types[0] == "run.start" and types[-1] == "run.end"
    assert types.count("model.call") == 1
    assert types.count("tool.call") == 1


def test_emitted_cassette_passes_the_repo_validator(tmp_path):
    path = _basic_run().write(tmp_path / "demo")
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(repo / "tools" / "validate_cassette.py"), str(path.parent)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_emitted_cassette_can_be_replayed_by_reference(tmp_path):
    """我们自己的 replay 至少要能把它读进来（argv 指向的假 agent 可执行）。"""
    path = _basic_run().write(tmp_path / "demo")
    events = read_cassette(path)
    assert events[0]["argv"] == ["python", "agent.py"]


def test_write_before_end_is_refused(tmp_path):
    run = emit.Run(agent="x", argv=[])
    run.model_result("hi")
    with pytest.raises(emit.EmitError):
        run.write(tmp_path / "nope")


def test_append_after_end_is_refused():
    run = _basic_run()
    with pytest.raises(emit.EmitError):
        run.tool_call("late")


def test_timestamps_are_monotonic_and_relative():
    run = _basic_run()
    ts = [e["t"] for e in run.events]
    assert ts == sorted(ts)
    assert ts[0] >= 0
