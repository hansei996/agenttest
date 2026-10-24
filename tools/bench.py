#!/usr/bin/env python3
"""bench —— 补上 docs/VERIFY.md 里自己承认的那个缺口：没有性能基准。

它做的事：生成一份 N 条事件的合法 cassette（真哈希链），然后量四条路径的耗时：
  1. validate   校验 12 条规则
  2. view       生成单文件 HTML（含 30k 上限的截断逻辑）
  3. regress    汇总断言并出报告
  4. flaky      判定不稳定（同一份 cassette 复制成多个 run）

默认 N=30000（查看器软上限就是 30000，正好压在上限上测）。
用法：
    python tools/bench.py                 # 人读
    python tools/bench.py --quick         # CI 冒烟：N=2000 + 阈值断言
    python tools/bench.py --n 100000      # 压到软上限之外，看截断行为
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from agenttest.cassette import write_cassette  # noqa: E402

# CI 冒烟阈值（宽松到只拦真正的退化，不拦机器慢）
LIMITS = {
    "validate": 30.0,
    "view": 60.0,
    "regress": 60.0,
    "flaky": 60.0,
}


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def build(n, path):
    events = [{
        "type": "run.start",
        "agent": "bench-agent",
        "argv": ["bench"],
        "cwd": ".",
        "env_fingerprint": "bench",
        "t": 0.0,
    }]
    for i in range(n - 2):
        if i % 3 == 0:
            events.append({"type": "tool.call", "name": "read_file", "args": {"path": "logs/a.log"}, "t": round(i / 1000, 3)})
        elif i % 3 == 1:
            events.append({"type": "tool.result", "name": "read_file", "ok": True, "bytes": 64, "t": round(i / 1000, 3)})
        else:
            events.append({
                "type": "model.result",
                "text": "quote_error 出现在日志第 " + str(i) + " 行",
                "tool_calls": [],
                "usage": {"in": 10, "out": 5},
                "t": round(i / 1000, 3),
            })
    events.append({"type": "run.end", "exit_code": 0, "files_changed": [], "t": round(n / 1000, 3)})
    return write_cassette(path, events)


def timed(label, args):
    start = time.perf_counter()
    proc = subprocess.run(args, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.perf_counter() - start
    ok = proc.returncode == 0
    return {"step": label, "seconds": round(elapsed, 2), "ok": ok,
            "detail": ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-1][:90] if (proc.stdout or proc.stderr) else ""}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30000)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    n = 2000 if args.quick else args.n
    py = sys.executable
    tmp = Path(tempfile.mkdtemp(prefix="agenttest-bench-"))
    try:
        cassette_dir = tmp / "run-1"
        t0 = time.perf_counter()
        build(n, cassette_dir)
        build_seconds = round(time.perf_counter() - t0, 2)
        size_mb = round(sum(p.stat().st_size for p in cassette_dir.glob("*")) / 1024 / 1024, 1)

        rows = [timed("validate", [py, "tools/validate_cassette.py", str(cassette_dir)])]
        rows.append(timed("view", [py, "tools/cassette_view.py", str(cassette_dir), "--out", str(tmp / "view.html")]))

        batch = tmp / "batch"
        batch.mkdir()
        for i in range(3):
            shutil.copytree(cassette_dir, batch / ("run-" + str(i)))
        rows.append(timed("regress", [py, "-m", "agenttest", "regress", str(batch), "--assert", "before:quote_error", "--out", str(tmp / "rep")]))
        rows.append(timed("flaky", [py, "-m", "agenttest", "flaky", str(batch), "--assert", "before:quote_error"]))

        result = {"events": n, "size_mb": size_mb, "build_seconds": build_seconds, "steps": rows}
        failures = [r["step"] for r in rows if not r["ok"]]
        slow = [r["step"] for r in rows if r["seconds"] > LIMITS.get(r["step"], 999)]

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("bench：%d 条事件 / %.1f MB（生成耗时 %.2fs）" % (n, size_mb, build_seconds))
            print("  %-9s %8s  %s" % ("步骤", "秒", "最后一行输出"))
            for row in rows:
                print("  %-9s %8.2f  %s%s" % (row["step"], row["seconds"], "" if row["ok"] else "[非零退出] ", row["detail"]))
        if failures:
            print("BENCH FAIL: 这些步骤没跑通：" + ", ".join(failures))
            return 1
        if slow:
            print("BENCH FAIL: 超过阈值：" + ", ".join(slow))
            return 1
        print("BENCH OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    _force_utf8()
    sys.exit(main(sys.argv[1:]))
