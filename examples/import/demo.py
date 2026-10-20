"""把两份示例日志导入成 cassette，并当场验证哈希链、断言与跨格式 diff。

    PYTHONPATH=src python examples/import/demo.py --out .work/import-demo

两份示例录的是同一段对话：一段是 OpenAI Chat Completions 风格（每轮带 created
时间戳），一段是 Anthropic Messages 风格（没有时间戳，走合成时间路径）。
最后一步 diff 会把两者对比给你看：格式不同，行为相同。
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from agenttest import assertions as asrt
from agenttest.cassette import chain_head, read_cassette
from agenttest.diff import diff_runs
from agenttest.importers import load

BASE = Path(__file__).resolve().parent
SAMPLES = (
    (BASE / "openai-sample.jsonl", "openai-chat"),
    (BASE / "anthropic-sample.json", "anthropic-messages"),
)
ASSERTS = ["before:quote_error", "tool:read_file(path=src/auth.py)", "never:tool=delete_file", "exit:0"]


def import_one(source, label, out):
    cassette = load(source)
    path = cassette.write(out / label)
    events = read_cassette(path)
    twice = load(source)
    print("=" * 78)
    print(label + "  <-  " + source.name)
    print("  事件      " + str(len(events)) + " 条  " + str(cassette.counts))
    print("  合成时间戳 " + ("是（日志没有时间戳，t 由事件序号合成）" if cassette.synthetic_timestamps else "否（沿用日志里的 created）"))
    print("  链头      " + chain_head(path))
    print(
        "  确定性    两次 load 逐事件一致："
        + ("是" if twice.events == cassette.events else "否")
        + "，两次写盘逐字节一致："
        + ("是" if twice.write(out / (label + "-again")).read_bytes() == path.read_bytes() else "否")
    )
    print("  warnings  " + str(len(cassette.warnings)) + " 条")
    for item in cassette.warnings:
        print("    - " + item)
    print("  cassette 头 5 行（原文）：")
    for line in path.read_text(encoding="utf-8").splitlines()[:5]:
        print("    " + line)
    print("  断言（直接跑在导入的事件流上）：")
    for result in asrt.evaluate_all(ASSERTS, events):
        print("    " + ("PASS " + result.expr if result.ok else result.message))
    return cassette, events


def main(argv=None):
    parser = argparse.ArgumentParser(description="importers 示例：日志 -> cassette -> 校验/diff")
    parser.add_argument(
        "--out",
        default=None,
        help="cassette 写到哪（默认临时目录）",
    )
    args = parser.parse_args(argv)

    holder = None
    if args.out:
        out = Path(args.out)
    else:
        holder = tempfile.TemporaryDirectory(prefix="agenttest-import-demo-")
        out = Path(holder.name)
    out.mkdir(parents=True, exist_ok=True)
    print("cassette 输出目录：" + out.as_posix())

    imported = [import_one(source, label, out) for source, label in SAMPLES]

    print("=" * 78)
    print("跨格式 diff（同一段对话，两种日志格式）")
    print(
        diff_runs(
            imported[0][1],
            imported[1][1],
            SAMPLES[0][1] + " (openai)",
            SAMPLES[1][1] + " (anthropic)",
        )
    )
    if holder is not None:
        holder.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
