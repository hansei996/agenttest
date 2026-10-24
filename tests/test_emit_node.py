"""跨语言证明：Node 写出的 cassette 必须能过我们自己的校验器。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑跨语言证明")


def test_node_emitter_output_passes_the_validator(tmp_path):
    out = tmp_path / "node-out"
    produced = subprocess.run(
        ["node", str(REPO / "examples" / "emit-node" / "emit.mjs"), str(out)],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert produced.returncode == 0, produced.stdout + produced.stderr
    assert (out / "cassette.jsonl").exists()

    checked = subprocess.run(
        [sys.executable, str(REPO / "tools" / "validate_cassette.py"), str(out)],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "12 条规则全部通过" in checked.stdout
