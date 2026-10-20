"""tools/reference_reader.py：一个第三方实现必须能读懂同一份 cassette。

这份测试是 ROADMAP v1.0 验收数字的自动版：「至少一个第三方实现能读写同一份
cassette」。reference_reader 不 import agenttest、也不 import 校验器，只照
docs/CASSETTE-SPEC.md 写，所以它能读通就说明规范本身是可实现的。
"""

from __future__ import annotations

import ast
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
READER = REPO / "tools" / "reference_reader.py"
SPEC = REPO / "docs" / "CASSETTE-SPEC.md"
GOOD = REPO / "examples" / "good" / "cassette.jsonl"
FENCE = chr(96) * 3


@pytest.fixture
def workdir():
    """临时目录（同 test_spec_validate：不用 mkdtemp 的 0o700 目录）。"""
    path = Path(tempfile.gettempdir()) / ("agenttest-ref-" + uuid.uuid4().hex)
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def run_reader(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run(
        [sys.executable, str(READER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def records_of(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rebuild(records: list) -> str:
    lines = []
    prev = None
    for index, record in enumerate(records):
        body = {"seq": index, "prev": prev, "event": record["event"]}
        line = {"seq": index, "prev": prev, "event": record["event"], "hash": ev.digest(body)}
        lines.append(json.dumps(line, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        prev = line["hash"]
    return "\n".join(lines) + "\n"


def test_reference_reader_reads_the_example_cassette():
    result = run_reader(str(GOOD))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK 20 条记录" in result.stdout
    assert "run.start 1" in result.stdout
    assert "tool.call 4" in result.stdout
    head = result.stdout.split("chain head: ")[1].strip()
    assert re.fullmatch(r"[0-9a-f]{64}", head)
    # 链头必须和实现自己算出来的一致
    assert head == records_of(GOOD)[-1]["hash"]


def test_reference_reader_accepts_a_directory():
    assert run_reader(str(REPO / "examples" / "good")).returncode == 0


def test_reference_reader_rejects_a_broken_chain(workdir):
    records = records_of(GOOD)
    records[5]["event"]["text"] = "tampered"
    lines = GOOD.read_text(encoding="utf-8").splitlines()
    lines[5] = json.dumps(records[5], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path = workdir / "cassette.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = run_reader(str(path))
    assert result.returncode == 1
    assert "第 6 行" in result.stdout
    assert "hash" in result.stdout


def test_reference_reader_rejects_a_missing_field(workdir):
    records = records_of(GOOD)
    records[4]["event"].pop("bytes")
    path = workdir / "cassette.jsonl"
    path.write_text(rebuild(records), encoding="utf-8")

    result = run_reader(str(path))
    assert result.returncode == 1
    assert "第 5 行" in result.stdout
    assert "bytes" in result.stdout


def test_reference_reader_rejects_an_unknown_event_type(workdir):
    records = records_of(GOOD)
    records[3]["event"]["type"] = "run.pause"
    path = workdir / "cassette.jsonl"
    path.write_text(rebuild(records), encoding="utf-8")

    result = run_reader(str(path))
    assert result.returncode == 1
    assert "第 4 行" in result.stdout
    assert "白名单" in result.stdout


def test_reference_reader_reads_every_spec_example(workdir):
    """规范里公布的三段示例，必须能被这个第三方实现直接读懂。"""
    text = SPEC.read_text(encoding="utf-8")
    blocks = re.findall(FENCE + r"jsonl\n(.*?)\n" + FENCE, text, re.S)
    assert len(blocks) == 3
    for index, block in enumerate(blocks):
        path = workdir / ("example-" + str(index) + ".jsonl")
        path.write_text(block + "\n", encoding="utf-8")
        result = run_reader(str(path))
        assert result.returncode == 0, result.stdout


def test_reference_reader_does_not_depend_on_the_implementation():
    """它必须是"第三方视角"：不许 import agenttest，也不许复用校验器。

    用 AST 判断真实 import 节点，而不是搜文本——文档字符串里写着"不 import agenttest"
    也是合法内容，搜文本会误报。
    """
    tree = ast.parse(READER.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert "agenttest" not in imported
    assert "validate_cassette" not in imported
    assert imported <= {"__future__", "json", "sys", "hashlib", "pathlib"}, imported


# --- 编码与 BOM -------------------------------------------------------------


def test_reference_reader_accepts_a_bom(workdir):
    """带 BOM 的同一份 cassette 必须读到同一批记录、同一个链头。"""
    raw = GOOD.read_bytes()
    path = workdir / "cassette.jsonl"
    path.write_bytes(b"\xef\xbb\xbf" + raw)

    with_bom = run_reader(str(path))
    without = run_reader(str(GOOD))
    assert with_bom.returncode == 0, with_bom.stdout + with_bom.stderr
    head_bom = with_bom.stdout.split("chain head: ")[1].strip()
    head_plain = without.stdout.split("chain head: ")[1].strip()
    assert head_bom == head_plain
    assert "OK 20 条记录" in with_bom.stdout


def test_reference_reader_rejects_utf16_with_advice(workdir):
    path = workdir / "cassette.jsonl"
    path.write_bytes(GOOD.read_text(encoding="utf-8").encode("utf-16"))

    result = run_reader(str(path))
    assert result.returncode == 1
    assert "UTF-16" in result.stdout
    assert "另存为 UTF-8（无 BOM）" in result.stdout

