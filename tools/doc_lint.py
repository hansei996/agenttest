#!/usr/bin/env python3
"""doc_lint —— 文档里写的每条命令，必须真的存在。

检查两件事：
  1. 所有 markdown / llms.txt 里出现的 agenttest <verb>，verb 必须是真实子命令；
  2. 同一条命令里出现的 --flag 必须是那个子命令接受的参数。

为什么要它：用户在文档里看到 agenttest imports（真名是 import），敲下去得到
unrecognized arguments，然后开始怀疑整个工具。这类错误在文档里几乎无法靠人眼发现。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from agenttest.cli import build_parser  # noqa: E402

SOURCES = ["README.md", "llms.txt", "docs/*.md", "docs/errors/*.md"]
PATTERN = re.compile(r"agenttest\s+([a-z][a-z-]*)([^\n|]*)")
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)
INLINE = re.compile(r"`([^`\n]+)`")
FLAG = re.compile(r"--([a-z][a-z-]+)")
# 英文散文里把 agenttest 当主语用，不是命令。显式列出，避免用正则去猜。
IGNORE = {("docs/ANNOUNCE.md", "records"), ("docs/ANNOUNCE.md", "replays")}


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def verbs_and_flags():
    """从真实 parser 里抽出 子命令 -> 该子命令接受的 --flag 集合。"""
    parser = build_parser()
    verbs = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                flags = set()
                for sub_action in sub._actions:
                    flags.update(sub_action.option_strings)
                verbs[name] = flags
    global_flags = set()
    for action in parser._actions:
        global_flags.update(action.option_strings)
    return verbs, global_flags


def code_spans(text):
    """只取围栏代码块：行内代码里的 agenttest emit 指的是模块，不是命令。"""
    return [m.group(1) for m in FENCE.finditer(text)]


def docs():
    for pattern in SOURCES:
        for path in sorted(REPO.glob(pattern)):
            yield path, path.read_text(encoding="utf-8")


def main() -> int:
    verbs, global_flags = verbs_and_flags()
    problems = []
    checked = 0
    for path, text in docs():
        rel = str(path.relative_to(REPO)).replace("\\", "/")
        spans = code_spans(text)
        for span in spans:
            for match in PATTERN.finditer(span):
                verb, rest = match.group(1), match.group(2)
                rest = rest.split(" -- ")[0]  # 裸 -- 之后的参数属于被调用的程序
                checked += 1
                if (rel, verb) in IGNORE:
                    continue
                if verb not in verbs:
                    problems.append("%s: agenttest %s -- 没有这个子命令（现有：%s）"
                                    % (rel, verb, ", ".join(sorted(verbs))))
                    continue
                allowed = verbs[verb] | global_flags
                for flag in FLAG.findall(rest):
                    if "--" + flag not in allowed:
                        problems.append("%s: agenttest %s --%s -- 该子命令不接受这个参数"
                                        % (rel, verb, flag))
    print("扫描命令示例：%d 条；子命令：%d 个" % (checked, len(verbs)))
    if problems:
        for item in problems:
            print("FAIL " + item)
        print("结果：%d 个问题" % len(problems))
        return 1
    print("DOC LINT OK")
    return 0


if __name__ == "__main__":
    _force_utf8()
    sys.exit(main())