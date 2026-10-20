"""cassette：JSONL + sha256 哈希链。"""

from __future__ import annotations

import json

import pytest

from agenttest import cassette as cas
from agenttest import events as ev


def sample_events():
    return [
        {
            "t": 0.0,
            "type": "run.start",
            "agent": "demo",
            "argv": ["python", "demo.py"],
            "cwd": "/repo",
            "env_fingerprint": "py3.12|linux",
        },
        {
            "t": 0.1,
            "type": "model.call",
            "model": "m",
            "request": {"messages": [], "tools": []},
        },
        {
            "t": 0.2,
            "type": "model.result",
            "text": "ok",
            "tool_calls": [],
            "usage": {"in": 1, "out": 1},
        },
        {"t": 0.3, "type": "run.end", "exit_code": 0, "files_changed": []},
    ]


def test_write_then_read_roundtrip(tmp_path):
    path = cas.write_cassette(tmp_path / "run", sample_events())
    assert path == tmp_path / "run" / "cassette.jsonl"
    assert cas.read_cassette(tmp_path / "run") == sample_events()


def test_chain_links_every_record(tmp_path):
    cas.write_cassette(tmp_path / "run", sample_events())
    lines = (tmp_path / "run" / "cassette.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert records[0]["prev"] is None
    for previous, current in zip(records, records[1:]):
        assert current["prev"] == previous["hash"]


def test_tampered_event_is_detected(tmp_path):
    cas.write_cassette(tmp_path / "run", sample_events())
    path = tmp_path / "run" / "cassette.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[2])
    record["event"]["text"] = "tampered"
    lines[2] = ev.canonical(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(tmp_path / "run")
    assert "第 3 条记录" in str(excinfo.value)


def test_missing_record_breaks_the_chain(tmp_path):
    cas.write_cassette(tmp_path / "run", sample_events())
    path = tmp_path / "run" / "cassette.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(tmp_path / "run")
    assert "哈希链断了" in str(excinfo.value) or "seq" in str(excinfo.value)


def test_unknown_event_type_is_rejected():
    with pytest.raises(ev.EventError) as excinfo:
        ev.validate({"t": 0.0, "type": "http.call"})
    assert "未知事件类型" in str(excinfo.value)


def test_missing_field_is_rejected():
    with pytest.raises(ev.EventError) as excinfo:
        ev.validate({"t": 0.0, "type": "run.end", "exit_code": 0})
    assert "files_changed" in str(excinfo.value)


def test_empty_cassette_is_refused(tmp_path):
    with pytest.raises(cas.CassetteError):
        cas.write_cassette(tmp_path / "run", [])
