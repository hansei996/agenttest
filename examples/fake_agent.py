"""一个假 agent：不真调模型，却真的读文件、改文件、跑测试。

它的"模型"是一份写死的脚本（--script good / bad），所以 record 不需要网络；
到了 replay，这些模型输出来自 cassette，脚本根本不会被调用。

    # 录制好行为
    python -m agenttest record examples/good -- python examples/fake_agent.py --script good
    # 按 cassette 重放
    python -m agenttest replay examples/good --assert before:quote_error
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from agenttest.agent import AgentError, CassetteExhausted, Session

BASE = Path(__file__).resolve().parent
APP = BASE / "app"
WORK = BASE / ".work"
PROMPT = "线上 /me 报 500，修一下 src/auth.py"

TOOLS = ["read_file", "edit_file", "run_tests"]

GOOD = [
    {
        "text": (
            "先看日志。日志里是 KeyError: 'quote_error'，来自 src/auth.py 第 4 行 "
            "return user['id']。先确认现场再动手。"
        ),
        "tool_calls": [{"name": "read_file", "args": {"path": "logs/app.log"}}],
        "usage": {"in": 900, "out": 120},
    },
    {
        "text": "现在读 src/auth.py，确认它直接下标取 id。",
        "tool_calls": [{"name": "read_file", "args": {"path": "src/auth.py"}}],
        "usage": {"in": 1100, "out": 90},
    },
    {
        "text": "把 user['id'] 换成 user.get('id')，报错引用的那条路径就不再炸。",
        "tool_calls": [
            {
                "name": "edit_file",
                "args": {"path": "src/auth.py", "find": "user['id']", "replace": "user.get('id')"},
            }
        ],
        "usage": {"in": 1350, "out": 70},
    },
    {
        "text": "跑测试确认不再抛 quote_error。",
        "tool_calls": [{"name": "run_tests", "args": {"target": "tests/test_auth.py"}}],
        "usage": {"in": 1500, "out": 40},
    },
    {
        "text": "修好了：改了 src/auth.py 的取值方式，测试通过。",
        "tool_calls": [],
        "usage": {"in": 1600, "out": 30},
    },
]

BAD = [
    {
        "text": "不用看日志，直接改：把 user['id'] 换成 user.get('id') 就行。",
        "tool_calls": [
            {
                "name": "edit_file",
                "args": {"path": "src/auth.py", "find": "user['id']", "replace": "user.get('id')"},
            }
        ],
        "usage": {"in": 800, "out": 60},
    },
    {
        "text": "顺手把 src/auth.py 读一眼，看看还有没有别的下标取值。",
        "tool_calls": [{"name": "read_file", "args": {"path": "src/auth.py"}}],
        "usage": {"in": 950, "out": 70},
    },
    {
        "text": "display_name 也用了下标，一起换掉。",
        "tool_calls": [
            {
                "name": "edit_file",
                "args": {
                    "path": "src/auth.py",
                    "find": "user['name']",
                    "replace": "user.get('name')",
                },
            }
        ],
        "usage": {"in": 1050, "out": 50},
    },
    {
        "text": "跑测试。",
        "tool_calls": [{"name": "run_tests", "args": {"target": "tests/test_auth.py"}}],
        "usage": {"in": 1150, "out": 30},
    },
    {
        "text": "改完了。",
        "tool_calls": [],
        "usage": {"in": 1200, "out": 20},
    },
]

SCRIPTS = {"good": GOOD, "bad": BAD}


def make_provider(script):
    """假模型：按录制脚本依次回答，只活在 record 阶段。"""
    queue = list(script)
    calls = {"n": 0}

    def provider(request):
        if not queue:
            raise RuntimeError("假模型脚本用完了：请给 --script 多加一步")
        calls["n"] += 1
        return queue.pop(0)

    return provider


def copy_template(source, target):
    """把模板复制进工作目录，并统一成 LF。

    git 的 core.autocrlf 在不同机器上会把模板 checkout 成 CRLF/ LF 两种样子；
    产物哈希记在 cassette 里，所以这里必须把内容钉死。
    """
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        data = path.read_bytes().replace(b"\r\n", b"\n")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def prepare_workdir(script):
    workdir = WORK / script
    if workdir.exists():
        shutil.rmtree(workdir)
    copy_template(APP, workdir)
    return workdir


def read_file(workdir):
    def handler(args):
        path = workdir / args["path"]
        if not path.is_file():
            raise FileNotFoundError(str(args["path"]))
        return path.read_text(encoding="utf-8")

    return handler


def edit_file(workdir):
    def handler(args):
        path = workdir / args["path"]
        text = path.read_text(encoding="utf-8")
        if args["find"] not in text:
            raise ValueError(args["path"] + " 里找不到 " + repr(args["find"]))
        path.write_text(text.replace(args["find"], args["replace"], 1), encoding="utf-8")
        return "已修改 " + args["path"] + ": " + args["find"] + " -> " + args["replace"]

    return handler


def run_tests(workdir):
    def handler(args):
        source = (workdir / "src/auth.py").read_text(encoding="utf-8")
        if "user['id']" in source:
            raise AssertionError("1 failed: KeyError: 'quote_error' 还在")
        return "1 passed"

    return handler


def handlers(workdir):
    return {
        "read_file": read_file(workdir),
        "edit_file": edit_file(workdir),
        "run_tests": run_tests(workdir),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="agenttest 示例：一个不真调模型的假 agent")
    parser.add_argument("--script", choices=sorted(SCRIPTS), default="good")
    args = parser.parse_args(argv)

    workdir = prepare_workdir(args.script)
    rel_workdir = Path(os.path.relpath(workdir, Path.cwd())).as_posix()
    ctx = Session(agent="fake_agent", workdir=rel_workdir, model="scripted-model")
    table = handlers(workdir)
    provider = make_provider(SCRIPTS[args.script])
    messages = [{"role": "user", "content": PROMPT}]
    changed = []
    exit_code = 0
    try:
        for _ in range(10):
            reply = ctx.model(messages, provider=provider, tools=TOOLS)
            messages.append({"role": "assistant", "content": reply["text"]})
            calls = reply.get("tool_calls") or []
            if not calls:
                break
            for call in calls:
                outcome = ctx.tool(call["name"], call["args"], table[call["name"]])
                if call["name"] in ("edit_file", "write_file") and outcome.ok:
                    path = call["args"]["path"]
                    if path not in changed:
                        changed.append(path)
                messages.append({"role": "tool", "content": outcome.output})
                if outcome.ok and call["name"] == "run_tests":
                    exit_code = 0
                elif not outcome.ok and call["name"] == "run_tests":
                    exit_code = 1
    except CassetteExhausted as exc:
        print("model.result 已用尽：" + str(exc), file=sys.stderr)
        return 3
    except AgentError as exc:
        print("agent 用法错误：" + str(exc), file=sys.stderr)
        return 2
    ctx.finish(exit_code=exit_code, files_changed=changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
