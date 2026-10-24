"""cassette_view：单文件查看器的行为锁。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "cassette_view.py"


def _run(*args):
    proc = subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_generates_a_self_contained_page(tmp_path):
    out = tmp_path / "view.html"
    code, text = _run(str(REPO / "examples" / "good"), "--out", str(out))
    assert code == 0, text
    html = out.read_text(encoding="utf-8")
    assert "哈希链完好" in html
    assert "http://" not in html and "https://" not in html, "页面不许引用任何外部资源"
    assert html.count("data-hay=") == 20


def test_missing_meta_is_reported_as_not_recorded(tmp_path):
    out = tmp_path / "view.html"
    _run(str(REPO / "examples" / "good"), "--out", str(out))
    html = out.read_text(encoding="utf-8")
    assert "没记" in html, "缺 meta.unobserved 时不许说成「都观测到了」"


def test_broken_chain_is_loud_and_exits_nonzero(tmp_path):
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    lines = (REPO / "examples" / "good" / "cassette.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[5])
    record["event"]["t"] = 99.0
    lines[5] = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    (tampered / "cassette.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "bad.html"
    code, text = _run(str(tampered), "--out", str(out))
    assert code == 1, text
    assert "哈希链在第" in text, text
    assert "哈希链断了" in out.read_text(encoding="utf-8")


def test_unobserved_list_is_surfaced(tmp_path):
    source = tmp_path / "with-meta"
    source.mkdir()
    lines = (REPO / "examples" / "good" / "cassette.jsonl").read_text(encoding="utf-8").splitlines()
    # 只在页面渲染层面验证：直接给 render 一份带 meta 的数据
    sys.path.insert(0, str(REPO / "tools"))
    import cassette_view

    records = [json.loads(line) for line in lines]
    records[0]["event"]["meta"] = {"unobserved": ["tool.call", "tool.result"]}
    html = cassette_view.render(
        {"records": records, "size": 1234, "truncated": False, "first_break": None, "path": source},
        "测试",
    )
    assert "未观测事件：tool.call、tool.result" in html