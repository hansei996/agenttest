"""cassette 编码：读容忍 UTF-8 BOM（Windows 记事本会加），写永远不带 BOM。"""

from __future__ import annotations

import json

import pytest

from agenttest import cassette as cas

BOM = b"\xef\xbb\xbf"


def bom_copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(BOM + source.read_bytes())
    return dest


def test_utf8_bom_cassette_reads_exactly_like_a_plain_one(tmp_path, examples):
    plain = cas.read_cassette(examples / "good")
    with_bom = cas.read_cassette(bom_copy(examples / "good" / "cassette.jsonl", tmp_path / "bom.jsonl"))
    assert with_bom == plain
    assert len(with_bom) == 20


def test_bom_does_not_break_the_hash_chain(tmp_path, examples):
    path = bom_copy(examples / "good" / "cassette.jsonl", tmp_path / "bom.jsonl")
    cas.read_cassette(path)  # verify=True：链必须照常通过
    assert cas.chain_head(path) == cas.chain_head(examples / "good")


def test_cli_replay_works_on_a_bom_cassette(run, tmp_path, examples):
    bom_copy(examples / "good" / "cassette.jsonl", tmp_path / "bom" / "cassette.jsonl")
    proc = run("replay", str(tmp_path / "bom"), "--assert", "before:quote_error")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "哈希链完整" in proc.stdout
    assert "PASS" in proc.stdout and "个断言全部通过" in proc.stdout


def test_cli_diff_works_on_bom_cassettes(run, tmp_path, examples):
    bom_copy(examples / "good" / "cassette.jsonl", tmp_path / "before" / "cassette.jsonl")
    bom_copy(examples / "bad" / "cassette.jsonl", tmp_path / "after" / "cassette.jsonl")
    proc = run("diff", str(tmp_path / "before"), str(tmp_path / "after"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "行为差异" in proc.stdout
    assert "quote_error" in proc.stdout


def test_written_cassette_has_no_bom_and_lf_only(tmp_path, examples):
    events = cas.read_cassette(examples / "good")
    path = cas.write_cassette(tmp_path / "out", events)
    raw = path.read_bytes()
    assert raw[:3] != BOM
    assert not raw.startswith(BOM)
    assert b"\r\n" not in raw
    assert raw.startswith(b'{"event"')
    assert cas.read_cassette(path) == events


def test_bom_roundtrip_is_stable(tmp_path, examples):
    events = cas.read_cassette(examples / "good")
    first = cas.write_cassette(tmp_path / "a", events).read_bytes()
    with_bom = tmp_path / "b.jsonl"
    with_bom.write_bytes(BOM + first)
    second = cas.write_cassette(tmp_path / "c", cas.read_cassette(with_bom)).read_bytes()
    assert second == first


def test_utf16_cassette_names_the_encoding(tmp_path):
    path = tmp_path / "cassette.jsonl"
    path.write_text('{"seq":0,"prev":null,"event":{},"hash":"x"}\n', encoding="utf-16")
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(path)
    message = str(excinfo.value)
    assert "UTF-16" in message
    assert "UTF-8" in message
    assert "不是合法 JSON" not in message


def test_binary_garbage_is_reported_as_binary(tmp_path):
    path = tmp_path / "cassette.jsonl"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 24)
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(path)
    message = str(excinfo.value)
    assert "二进制文件" in message
    assert "NUL" in message
    assert "不是合法 JSON" not in message


def test_invalid_utf8_is_not_blamed_on_json(tmp_path):
    path = tmp_path / "cassette.jsonl"
    path.write_bytes(b'{"seq":0,"prev":null,"event":{"agent":"\xff\xfe\xfd"},"hash":"x"}\n')
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(path)
    message = str(excinfo.value)
    assert "不是合法的 UTF-8 文本" in message
    assert "不是合法 JSON" not in message


def test_broken_json_says_it_is_not_an_encoding_problem(tmp_path):
    path = tmp_path / "cassette.jsonl"
    path.write_text('{"seq":0}\nnot json at all\n', encoding="utf-8")
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(path)  # 第 1 条缺 event 字段，先撞到结构错误
    assert "缺少 event 字段" in str(excinfo.value)

    path.write_text("not json at all\n", encoding="utf-8")
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(path)
    message = str(excinfo.value)
    assert "第 1 条记录不是合法 JSON" in message
    assert "不是编码问题" in message


def test_empty_file_says_it_is_empty(tmp_path):
    path = tmp_path / "cassette.jsonl"
    path.write_bytes(b"")
    with pytest.raises(cas.CassetteError) as excinfo:
        cas.read_cassette(path)
    assert "是空的" in str(excinfo.value)


def test_events_file_also_tolerates_bom(tmp_path):
    path = tmp_path / "events.jsonl"
    line = json.dumps({"t": 0.0, "type": "run.end", "exit_code": 0, "files_changed": []})
    path.write_bytes(BOM + line.encode("utf-8") + b"\n")
    events = cas.read_events_file(path)
    assert events == [{"t": 0.0, "type": "run.end", "exit_code": 0, "files_changed": []}]
