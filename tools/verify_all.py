#!/usr/bin/env python3
"""verify_all —— 把所有「我们声称过的事」变成可复跑的命令。

用法：
    python tools/verify_all.py                 # 逐条跑，打印 PASS/FAIL
    python tools/verify_all.py --write-doc     # 顺便重写 docs/VERIFY.md

为什么需要它：一轮轮开发攒下很多断言（跨语言可互操作、噪声不冒充退步、篡改必须被拒），
它们散在聊天记录和 commit message 里，等于没有。这里每条都是「命令 + 期望输出」，
谁不信就自己跑。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICK = chr(96)


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def sh(args):
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        args,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def checks(tmp):
    py = sys.executable
    items = []

    def add(claim, shown, ok, detail=""):
        items.append({"claim": claim, "command": shown, "ok": bool(ok), "detail": detail})

    code, out = sh([py, "-m", "agenttest", "demo"])
    add(
        "demo 一条命令自证：好 cassette PASS、坏 cassette FAIL",
        "python -m agenttest demo",
        code == 0 and "PASS" in out and "FAIL" in out,
        (out.strip().splitlines() or [""])[0],
    )

    code, out = sh([py, "-m", "agenttest", "replay", "examples/bad", "--assert", "before:quote_error"])
    add(
        "坏行为必须被断言抓住（replay 非零退出）",
        "python -m agenttest replay examples/bad --assert before:quote_error",
        code != 0,
        "exit=" + str(code),
    )

    code, out = sh([py, "tools/validate_cassette.py", "examples/good"])
    add(
        "校验器接受合规 cassette（12 条规则）",
        "python tools/validate_cassette.py examples/good",
        code == 0 and "12 条规则全部通过" in out,
        "exit=" + str(code),
    )

    tampered = tmp / "tampered"
    tampered.mkdir()
    lines = (REPO / "examples" / "good" / "cassette.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[5])
    rec["event"]["t"] = 99.0
    lines[5] = json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    (tampered / "cassette.jsonl").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    code, out = sh([py, "tools/validate_cassette.py", str(tampered)])
    add(
        "校验器拒绝被篡改的 cassette",
        "python tools/validate_cassette.py <被改过一个字节的副本>",
        code != 0,
        "exit=" + str(code),
    )

    node = shutil.which("node")
    if node:
        nodeout = tmp / "from-node"
        code, out = sh([node, "examples/emit-node/emit.mjs", str(nodeout)])
        code2, out2 = sh([py, "tools/validate_cassette.py", str(nodeout)])
        add(
            "Node 独立实现写出的 cassette 通过 Python 校验器",
            "node examples/emit-node/emit.mjs <dir> && python tools/validate_cassette.py <dir>",
            code == 0 and code2 == 0,
            "exit=" + str(code) + "/" + str(code2),
        )

    code, out = sh([py, "-c", "from agenttest.flaky import runs_needed; print(runs_needed(0.99))"])
    add(
        "统计主张有确切样本量：失败率 <=1% 需 381 次运行",
        "python -c 'from agenttest.flaky import runs_needed; print(runs_needed(0.99))'",
        out.strip() == "381",
        out.strip(),
    )

    code, out = sh([py, "tools/cassette_view.py", str(tampered), "--out", str(tmp / "v.html")])
    add(
        "查看器当场重算哈希链，断链时非零退出",
        "python tools/cassette_view.py <被篡改的 cassette>",
        code == 1 and "哈希链在第" in out,
        "exit=" + str(code),
    )

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONIOENCODING", "PYTHONUTF8"}}
    env["PYTHONPATH"] = "src"
    proc = subprocess.run([py, "tools/dogfood.py"], cwd=str(REPO), capture_output=True, env=env)
    out = proc.stdout.decode("utf-8", "replace")
    add(
        "剥掉编码环境变量后，中文输出仍按 UTF-8 可读",
        "python tools/dogfood.py   （不设 PYTHONIOENCODING）",
        proc.returncode == 0 and "噪声条数" in out,
        (out.strip().splitlines() or [""])[0],
    )

    return items


def render(items):
    ok = sum(1 for i in items if i["ok"])
    lines = [
        "# 可复跑的验证清单",
        "",
        "> 这份文件由 " + TICK + "python tools/verify_all.py --write-doc" + TICK + " 生成，不要手改。",
        "> 每一条都是「主张 → 命令 → 结果」，谁不信就自己跑一遍。",
        "",
        "当前结果：**" + str(ok) + " / " + str(len(items)) + " 通过**",
        "",
        "| # | 主张 | 复跑命令 | 结果 |",
        "|---|---|---|---|",
    ]
    for index, item in enumerate(items, 1):
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(
            "| " + str(index) + " | " + item["claim"] + " | " + TICK + item["command"] + TICK + " | " + mark + " |"
        )
    lines += [
        "",
        "## 这份清单**不**覆盖什么",
        "",
        "- 完整测试套件（" + TICK + "python -m pytest tests -q" + TICK + "）——它本身就是证据，不重复列。",
        "- Windows 与 Linux 的差异：CI 两个平台各跑一次，看 Actions 记录才算数。",
        "- 性能与规模：见 [docs/PERF.md](./PERF.md)（30k 事件四条路径的实测耗时与上限说明）。",
        "",
    ]
    return chr(10).join(lines)


def main(argv):
    tmp = Path(tempfile.mkdtemp(prefix="agenttest-verify-"))
    try:
        items = checks(tmp)
        for item in items:
            mark = "PASS" if item["ok"] else "FAIL"
            print(mark + "  " + item["claim"])
            print("      " + item["command"])
            if item["detail"]:
                print("      -> " + item["detail"][:160])
        ok = sum(1 for i in items if i["ok"])
        print()
        print("结果：" + str(ok) + " / " + str(len(items)) + " 通过")
        if "--write-doc" in argv:
            doc = REPO / "docs" / "VERIFY.md"
            doc.write_text(render(items), encoding="utf-8")
            print("已更新 " + str(doc))
        return 0 if ok == len(items) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    _force_utf8()
    sys.exit(main(sys.argv[1:]))