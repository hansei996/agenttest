"""record：真的能把一次运行录成可重放的 cassette。"""

from __future__ import annotations

import sys

from agenttest import cassette as cas
from agenttest.record import record, record_summary


def test_record_then_replay_roundtrip(tmp_path, repo, run):
    command = [sys.executable, "examples/fake_agent.py", "--script", "good"]
    outcome = record(tmp_path / "run", command, cwd=repo)
    assert cas.cassette_path(tmp_path / "run").exists()
    assert outcome.events[0]["type"] == "run.start"
    assert outcome.events[-1]["type"] == "run.end"
    assert "recorded" in record_summary(outcome)

    cas.read_cassette(tmp_path / "run")  # 哈希链必须完好
    proc = run("replay", str(tmp_path / "run"), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_record_via_cli(tmp_path, repo, run):
    proc = run(
        "record",
        str(tmp_path / "cli"),
        "--",
        sys.executable,
        "examples/fake_agent.py",
        "--script",
        "bad",
    )
    assert proc.returncode == 0, proc.stderr
    events = cas.read_cassette(tmp_path / "cli")
    assert len(events) == 20
    assert events[0]["argv"][0] == "python"
