"""agenttest demo —— 一条命令自证：录一次 → 重放 → 断言 → diff → 出报告。

不联网、不需要 API key、10 秒内跑完。目的是让人在 3 秒内看懂这个工具做什么。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def _repo_root() -> Path | None:
    """从包位置往上找 examples/ —— demo 需要示例 cassette。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "examples" / "good" / "cassette.jsonl").is_file():
            return parent
    return None


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "agenttest", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _first_fail_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAIL "):
            return stripped[len("FAIL "):]
    return "(未找到失败信息)"


def run_demo() -> int:
    root = _repo_root()
    if root is None:
        print("找不到 examples/ 目录：agenttest demo 需要在仓库根目录运行（或 pip install -e . 后从仓库里运行）。")
        return 1

    good = "examples/good"
    bad = "examples/bad"
    report_dir = Path(tempfile.mkdtemp(prefix="agenttest-demo-"))

    code_good, out_good = _run(["replay", good, "--assert", "before:quote_error"], root)
    code_bad, out_bad = _run(["replay", bad, "--assert", "before:quote_error"], root)
    code_diff, out_diff = _run(["diff", good, bad], root)
    code_report, out_report = _run(
        ["regress", "examples", "--assert", "before:quote_error", "--out", str(report_dir), "--html"], root
    )

    diff_lines = [l.strip() for l in out_diff.splitlines() if l.strip().startswith(("+", "-", "~"))]
    diff_summary = " · ".join(l[1:].strip() for l in diff_lines[:3]) or "(无差异)"

    print()
    print("agenttest demo — 让 agent 的行为可以被断言")
    print()
    print(f"  {'PASS' if code_good == 0 else 'FAIL'}  replay examples/good   守规矩：先引用报错再改代码")
    print(f"  {'PASS' if code_bad == 0 else 'FAIL'}  replay examples/bad    偷懒：第 4 个事件就 edit_file，全程没引用报错")
    print(f"  行为差异               {diff_summary}")
    print(f"  回归报告               {(report_dir / 'index.html') if code_report == 0 else '(未生成)'}")
    print()
    print("  同一个 agent，一次守规矩一次偷懒 —— 工具抓得出区别。")
    print("  下一步：agenttest replay <你的 cassette> --assert before:quote_error")
    print()

    if code_bad != 0:
        print("  失败信息原文：")
        print("    " + _first_fail_line(out_bad))
        print()

    ok = code_good == 0 and code_bad != 0 and code_diff == 0
    return 0 if ok else 1
