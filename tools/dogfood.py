"""dogfood —— 用真实命令走一遍「不稳定断言 → 噪声分栏」的工作流，并断言结果。

为什么需要它：flaky / regress --flaky-report 这两条路径此前只有单元测试，
没有一条命令证明它们在真实仓库里连起来能用。CI 里跑这个脚本，等于每天问一次
「这两个功能还是活的吗」。

场景：同一个 run-1，基线是好的 cassette，现在的是坏的，
并且 flaky 报告把 before:quote_error 标成 MIXED_OBSERVED。期望：
  * regress 把它放进噪声栏（newly_failing_noisy），不是退步栏；
  * 终端输出里必须出现「噪声失败」和「被分栏而不是被隐藏」；
  * HTML 报告里也要有噪声那一节。

退出码 0 表示这条工作流仍然成立。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "agenttest", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def fail(message, output=""):
    print("DOGFOOD FAIL: " + message)
    if output:
        print(output[-1200:])
    sys.exit(1)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="agenttest-dogfood-"))
    try:
        base = tmp / "base" / "run-1"
        base.parent.mkdir(parents=True)
        shutil.copytree(REPO / "examples" / "good", base)
        cur = tmp / "cur" / "run-1"
        cur.parent.mkdir(parents=True)
        shutil.copytree(REPO / "examples" / "bad", cur)

        code, out = run("regress", str(tmp / "base"), "--assert", "before:quote_error", "--out", str(tmp / "baseline"))
        if code != 0:
            fail("基线 regress 失败", out)

        flaky = {
            "schema_version": "0.1.0",
            "generated_at": "dogfood",
            "min_runs": 5,
            "runs": 5,
            "unreliable": False,
            "asserts": [{
                "expr": "before:quote_error",
                "runs": 5,
                "passed": 3,
                "pass_rate": 0.6,
                "low": 0.23,
                "high": 0.88,
                "verdict": "MIXED_OBSERVED",
                "legacy": "FLAKY",
                "noisy": True,
                "note": "dogfood",
            }],
        }
        flaky_path = tmp / "flaky.json"
        flaky_path.write_text(json.dumps(flaky), encoding="utf-8")

        code, out = run(
            "regress", str(tmp / "cur"),
            "--assert", "before:quote_error",
            "--baseline", str(tmp / "baseline" / "report.json"),
            "--flaky-report", str(flaky_path),
            "--out", str(tmp / "now"),
            "--html",
        )
        if "噪声失败" not in out:
            fail("终端输出里没有噪声栏", out)
        if "被分栏而不是被隐藏" not in out:
            fail("缺少「被分栏而不是被隐藏」那句提示", out)

        report = json.loads((tmp / "now" / "report.json").read_text(encoding="utf-8"))
        comparison = report.get("comparison") or {}
        if comparison.get("newly_failing"):
            fail("已知不稳定的断言仍被算成退步", json.dumps(comparison, ensure_ascii=False)[:800])
        if not comparison.get("newly_failing_noisy"):
            fail("噪声栏是空的", json.dumps(comparison, ensure_ascii=False)[:800])

        html = (tmp / "now" / "index.html").read_text(encoding="utf-8")
        if "噪声失败" not in html:
            fail("HTML 报告里没有噪声那一节")

        print("DOGFOOD OK")
        print("  噪声条数      " + str(len(comparison["newly_failing_noisy"])))
        print("  硬退步条数    " + str(len(comparison.get("newly_failing") or [])))
        print("  终端提示      有")
        print("  HTML 噪声节   有")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
