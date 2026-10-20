"""docs/CASSETTE-SPEC.md 与 tools/validate_cassette.py 的一致性闸门。

这批测试有两个职责：

1. 证明校验器在真 cassette 上通过、在两类损坏样本上失败（退出码 + 行号 + 规则号）。
2. 证明"规范 / JSON Schema / 校验器 / 实现"四份东西没有漂移——任何一侧改了字段名、
   事件名或规则编号，这里就红。所以它同时是 CASSETTE-SPEC 的回归测试。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

from agenttest import events as ev

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "validate_cassette.py"
SPEC = REPO / "docs" / "CASSETTE-SPEC.md"
SCHEMA = REPO / "docs" / "cassette.schema.json"
GOOD = REPO / "examples" / "good" / "cassette.jsonl"
FENCE = chr(96) * 3


def _load_tool():
    spec = importlib.util.spec_from_file_location("validate_cassette_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


@pytest.fixture
def workdir():
    """放样本文件的临时目录。

    有意不用 pytest 的 tmp_path：它用 mkdtemp 建 0o700 目录，而受限沙箱（本机的
    DSH 沙箱、以及一些企业策略）会拒绝对这种目录写入或枚举。这里用默认权限建目录，
    清理尽力而为。
    """
    path = Path(tempfile.gettempdir()) / ("agenttest-spec-" + uuid.uuid4().hex)
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def run_tool(*args: str) -> subprocess.CompletedProcess:
    """跑校验器。

    两处都显式钉死 UTF-8，不依赖运行环境的代码页：
    * 子进程侧由 tools/validate_cassette.py 的 _force_utf8() 负责；
    * 父进程侧在这里写死 encoding，并主动从环境里摘掉 PYTHONIOENCODING，
      这样测试既不靠 locale，也不靠谁在外面 export 了变量。
    """
    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def records_of(path: Path) -> list:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def rebuild(records: list) -> str:
    """按实现重算整条链，把改动"洗干净"，让别的规则可以单独暴露。"""
    lines = []
    prev = None
    for index, record in enumerate(records):
        body = {"seq": index, "prev": prev, "event": record["event"]}
        line = {"seq": index, "prev": prev, "event": record["event"], "hash": ev.digest(body)}
        lines.append(json.dumps(line, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        prev = line["hash"]
    return "\n".join(lines) + "\n"


def write_sample(directory: Path, text: str, name: str = "cassette.jsonl") -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


# --- 四份东西不许漂移 -------------------------------------------------------


def test_tool_tables_match_implementation():
    """校验器里硬编码的白名单 / 必填字段必须和 src/agenttest/events.py 逐字一致。"""
    assert tool.EVENT_TYPES == ev.EVENT_TYPES
    assert tool.REQUIRED_FIELDS == ev.REQUIRED_FIELDS


def test_schema_matches_implementation():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    defs = schema["$defs"]
    for etype in ev.EVENT_TYPES:
        node = defs[etype]
        assert node["properties"]["type"]["const"] == etype
        assert tuple(node["required"]) == ("type",) + ev.REQUIRED_FIELDS[etype]
    refs = [item["$ref"].rsplit("/", 1)[-1] for item in defs["event"]["oneOf"]]
    assert sorted(refs) == sorted(ev.EVENT_TYPES)
    assert defs["record"]["required"] == ["seq", "prev", "event", "hash"]


def test_spec_documents_every_rule_and_nothing_more():
    """规范里的规则表与校验器的 RULES 必须一一对应（多了少了都算漂移）。"""
    text = SPEC.read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| (S\d+) \|", text, re.M))
    implemented = {rule for rule, _title in tool.RULES}
    assert documented == implemented
    assert len(implemented) == 12
    assert "--list-rules" in text


def test_spec_examples_are_real_cassettes():
    """规范里的三段示例必须是真能过校验器的 cassette，不是示意。"""
    text = SPEC.read_text(encoding="utf-8")
    pattern = FENCE + r"jsonl\n(.*?)\n" + FENCE
    blocks = re.findall(pattern, text, re.S)
    assert len(blocks) == 3
    for block in blocks:
        findings = tool.validate_text(block)
        failed = [f for f in findings if not f.ok]
        assert failed == [], [f.rule + ": " + f.message for f in failed]


def test_spec_hash_example_is_self_consistent():
    """第 3.4 节那个"手算核对"的例子必须真的算得出来。"""
    body = {
        "seq": 0,
        "prev": None,
        "event": {
            "agent": "demo_agent",
            "argv": ["python", "demo_agent.py"],
            "cwd": "/repo",
            "env_fingerprint": "py3.12|linux",
            "t": 0.0,
            "type": "run.start",
            "workdir": ".",
        },
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert len(canonical) == 174
    assert ev.digest(body) == "657f26acb5a27e6f33f0a58a4fd1742d2a62f04e5a961c4bd2740a2859bd66d1"
    assert canonical in SPEC.read_text(encoding="utf-8")


# --- 校验器的行为 -----------------------------------------------------------


def test_tool_output_is_pure_utf8(workdir):
    """回归：不设 PYTHONIOENCODING 时，校验器的中文输出也必须是干净 UTF-8。

    这就是 Windows 上会红的那条：子进程按系统代码页（cp936）编码、父进程按 utf-8
    解码，于是"第 N 行"永远匹配不上。run_tool 已经摘掉 PYTHONIOENCODING，所以
    这条测试在 Linux CI 与 Windows 上都验的是同一件事。
    """
    records = records_of(GOOD)
    records[5]["event"]["text"] = "tampered"
    lines = GOOD.read_text(encoding="utf-8").splitlines()
    lines[5] = json.dumps(records[5], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path = write_sample(workdir, "\n".join(lines) + "\n")

    result = run_tool(str(path))
    assert "\ufffd" not in result.stdout
    assert "第 6 行" in result.stdout
    assert "S5" in result.stdout


def test_example_cassettes_pass():
    result = run_tool(str(REPO / "examples" / "good"), str(REPO / "examples" / "bad"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: 2/2" in result.stdout
    assert "FAIL" not in result.stdout


def test_broken_hash_chain_fails_with_line_and_rule(workdir):
    records = records_of(GOOD)
    records[5]["event"]["text"] = str(records[5]["event"].get("text", "")) + " (tampered)"
    lines = GOOD.read_text(encoding="utf-8").splitlines()
    lines[5] = json.dumps(records[5], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path = write_sample(workdir, "\n".join(lines) + "\n")

    result = run_tool(str(path))
    assert result.returncode == 1
    assert "S5" in result.stdout
    assert "第 6 行" in result.stdout


def test_missing_required_field_fails_with_line_and_rule(workdir):
    records = records_of(GOOD)
    removed = records[4]["event"].pop("bytes")
    path = write_sample(workdir, rebuild(records))

    result = run_tool(str(path))
    assert result.returncode == 1
    assert "S8" in result.stdout
    assert "第 5 行" in result.stdout
    assert "bytes" in result.stdout
    assert removed is not None


def test_unknown_event_field_is_ignored(workdir):
    """前向兼容：不认识的字段不许报错（S12）。"""
    records = records_of(GOOD)
    for record in records:
        record["event"]["x_future_field"] = {"nested": [1, 2, 3]}
    path = write_sample(workdir, rebuild(records))

    result = run_tool(str(path))
    assert result.returncode == 0, result.stdout
    assert "S12" in result.stdout
    assert "x_future_field" in result.stdout


def test_unknown_event_type_is_rejected(workdir):
    """类型白名单是封闭的：未知 type 不是"忽略"（S7）。"""
    records = records_of(GOOD)
    records[3]["event"]["type"] = "run.pause"
    path = write_sample(workdir, rebuild(records))

    result = run_tool(str(path))
    assert result.returncode == 1
    assert "S7" in result.stdout
    assert "第 4 行" in result.stdout


def test_schema_version_guard(workdir):
    records = records_of(GOOD)
    records[0]["event"]["schema_version"] = "9.9.9"
    bad = write_sample(workdir, rebuild(records), "bad-version.jsonl")
    result = run_tool(str(bad))
    assert result.returncode == 1
    assert "S9" in result.stdout

    records[0]["event"]["schema_version"] = "0.1.0"
    good = write_sample(workdir, rebuild(records), "good-version.jsonl")
    assert run_tool(str(good)).returncode == 0


def test_non_canonical_line_fails(workdir):
    """S6：行必须是 canonical JSON，多加一个空格也不算合规。"""
    lines = GOOD.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True)
    path = write_sample(workdir, "\n".join(lines) + "\n")

    result = run_tool(str(path))
    assert result.returncode == 1
    assert "S6" in result.stdout


def test_deleted_record_breaks_seq(workdir):
    lines = GOOD.read_text(encoding="utf-8").splitlines()
    path = write_sample(workdir, "\n".join(lines[:3] + lines[4:]) + "\n")

    result = run_tool(str(path))
    assert result.returncode == 1
    assert "S3" in result.stdout


def test_empty_file_is_rejected(workdir):
    path = write_sample(workdir, "")
    result = run_tool(str(path))
    assert result.returncode == 1
    assert "S1" in result.stdout


def test_reference_writer_output_passes(workdir):
    """实现写出来的东西必须过校验器——否则是规范写错了。"""
    from agenttest import cassette as cas

    events = [record["event"] for record in records_of(GOOD)]
    cas.write_cassette(workdir / "fresh", events)
    result = run_tool(str(workdir / "fresh"))
    assert result.returncode == 0, result.stdout
