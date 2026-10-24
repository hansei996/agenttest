"""文档里的每条命令都必须能跑：agenttest 的子命令与参数要和 CLI 对得上。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_doc_lint_passes():
    proc = subprocess.run(
        [sys.executable, "tools/doc_lint.py"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DOC LINT OK" in proc.stdout
    assert "扫描命令示例" in proc.stdout


def test_linter_would_catch_a_missing_subcommand(tmp_path):
    """证明这个 lint 不是恒真：塞一条假命令进去，它必须报错。"""
    victim = REPO / "docs" / "errors" / "index.md"
    original = victim.read_text(encoding="utf-8")
    try:
        victim.write_text(original + "\n```bash\nagenttest definitely-not-a-verb\n```\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "tools/doc_lint.py"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 1
        assert "definitely-not-a-verb" in proc.stdout
    finally:
        victim.write_text(original, encoding="utf-8")
