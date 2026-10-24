"""bench：性能冒烟必须能跑通，且阈值逻辑真的会拦人。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_quick_bench_passes():
    proc = subprocess.run(
        [sys.executable, "tools/bench.py", "--quick"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={"PYTHONPATH": "src"}.copy() | {k: v for k, v in __import__("os").environ.items()},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BENCH OK" in proc.stdout


def test_perf_doc_records_the_limits_the_code_uses():
    doc = (REPO / "docs" / "PERF.md").read_text(encoding="utf-8")
    view = (REPO / "tools" / "cassette_view.py").read_text(encoding="utf-8")
    assert "30,000" in doc and "SOFT_EVENT_CAP = 30_000" in view
    assert "500 MB" in doc and "HARD_BYTE_CAP = 500 * 1024 * 1024" in view
    assert "这份基准**不**证明什么" in doc, "基准页必须写清它不证明什么"
