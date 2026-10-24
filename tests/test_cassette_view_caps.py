"""查看器的上限行为：截断必须说出来，超硬上限必须拒绝。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import cassette_view  # noqa: E402


def _write_many(tmp_path, count):
    from agenttest.cassette import write_cassette

    events = [{"type": "run.start", "agent": "cap", "argv": ["x"], "cwd": ".",
               "env_fingerprint": "cap", "t": 0.0}]
    for i in range(count - 2):
        events.append({"type": "tool.result", "name": "read_file", "ok": True, "bytes": i, "t": round(i / 1000, 3)})
    events.append({"type": "run.end", "exit_code": 0, "files_changed": [], "t": 1.0})
    return write_cassette(tmp_path, events)


def test_truncation_is_announced_not_silent(tmp_path):
    path = _write_many(tmp_path, cassette_view.SOFT_EVENT_CAP + 500)
    data = cassette_view.load(path)
    assert len(data["records"]) == cassette_view.SOFT_EVENT_CAP
    assert data["truncated"] is True
    html = cassette_view.render(data, "截断测试")
    assert "已截断" in html
    assert str(cassette_view.SOFT_EVENT_CAP) in html


def test_a_normal_cassette_is_not_marked_truncated(tmp_path):
    path = _write_many(tmp_path, 50)
    data = cassette_view.load(path)
    assert data["truncated"] is False
    assert "已截断" not in cassette_view.render(data, "正常")


def test_hard_cap_refuses_instead_of_freezing(tmp_path, monkeypatch):
    path = _write_many(tmp_path, 20)
    monkeypatch.setattr(cassette_view, "HARD_BYTE_CAP", 16)
    with pytest.raises(SystemExit) as exc:
        cassette_view.load(path)
    assert "硬上限" in str(exc.value)
    assert "grep" in str(exc.value) or "jq" in str(exc.value), "拒绝时要告诉用户下一步怎么做"


def test_cli_reports_the_truncated_count(tmp_path, capsys):
    src = _write_many(tmp_path / "run", cassette_view.SOFT_EVENT_CAP + 10)
    code = cassette_view.main([str(src.parent), "--out", str(tmp_path / "v.html")])
    assert code == 0
    out = capsys.readouterr().out
    assert str(cassette_view.SOFT_EVENT_CAP) in out
