"""CLI: agenttest import —— 日志导入的端到端接线测试。"""

from __future__ import annotations

import json

from agenttest import cli
from agenttest.cassette import read_cassette

OPENAI = "examples/import/openai-sample.jsonl"
ANTHROPIC = "examples/import/anthropic-sample.json"


def test_import_openai_writes_valid_cassette(tmp_path):
    out = tmp_path / "o"
    assert cli.main(["import", OPENAI, str(out)]) == 0

    path = out / "cassette.jsonl"
    assert path.exists()
    events = read_cassette(path)  # verify=True：哈希链必须对
    types = [e["type"] for e in events]
    assert types[0] == "run.start" and types[-1] == "run.end"
    assert types.count("model.call") == types.count("model.result")


def test_import_anthropic_explicit_format(tmp_path):
    out = tmp_path / "a"
    assert cli.main(["import", ANTHROPIC, str(out), "--format", "anthropic"]) == 0
    events = read_cassette(out / "cassette.jsonl")
    start = events[0]
    assert start["meta"]["synthetic_timestamps"] is True


def test_import_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json at all\n", encoding="utf-8")
    out = tmp_path / "x"
    assert cli.main(["import", str(bad), str(out)]) == 1
    assert not (out / "cassette.jsonl").exists()


def test_import_exit_code_option(tmp_path):
    out = tmp_path / "c"
    assert cli.main(["import", OPENAI, str(out), "--exit-code", "3"]) == 0
    events = read_cassette(out / "cassette.jsonl")
    assert events[-1]["exit_code"] == 3
