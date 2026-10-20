"""CLI：四个动词 record / replay / diff / stat（argparse，不引第三方库）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import assertions as asrt
from . import stat as st
from .cassette import CassetteError, cassette_path, read_cassette
from .diff import diff_runs
from .process import ProcessError
from .record import RecordError, record, record_summary
from .replay import ReplayError, replay

EXIT_OK = 0
EXIT_FAIL = 1


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenttest",
        description="把 agent 的行为当代码来测：record / replay / diff / stat",
    )
    subs = parser.add_subparsers(dest="verb", required=True)

    rec = subs.add_parser("record", help="跑一次 agent，把事件流落成 cassette")
    rec.add_argument("target", help="cassette 目录，例如 examples/good")
    rec.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="同一任务跑 N 次，产出 batch.jsonl（给 stat 用）",
    )
    rec.add_argument(
        "--assert",
        dest="asserts",
        action="append",
        default=[],
        metavar="EXPR",
        help="把断言结果算进 batch 的成功判定，可重复",
    )
    rec.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="要录制的 agent 命令，写在 -- 之后",
    )

    rep = subs.add_parser("replay", help="按 cassette 重放并跑断言")
    rep.add_argument("target", help="cassette 目录，例如 examples/bad")
    rep.add_argument(
        "--assert",
        dest="asserts",
        action="append",
        default=[],
        metavar="EXPR",
        help="断言，可重复：before:quote_error / touched:src/auth.py / exit:0 ...",
    )

    dif = subs.add_parser("diff", help="结构化输出两次运行的行为差异")
    dif.add_argument("before", help="旧 cassette")
    dif.add_argument("after", help="新 cassette")

    sta = subs.add_parser("stat", help="对 record --repeat 的 batch 做统计判定")
    sta.add_argument("path", help="batch.jsonl，或 record --repeat 的目录")
    sta.add_argument(
        "--assert",
        dest="asserts",
        action="append",
        default=[],
        metavar="EXPR",
        help="统计断言，可重复：success>=0.8 / tokens<=2000 / duration<=5 ...",
    )
    return parser


def main(argv: list | None = None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verb == "record":
        return _cmd_record(args, parser)
    if args.verb == "replay":
        return _cmd_replay(args, parser)
    if args.verb == "diff":
        return _cmd_diff(args)
    if args.verb == "stat":
        return _cmd_stat(args)
    parser.error("未知子命令：" + str(args.verb))
    return EXIT_FAIL


def _cmd_record(args, parser: argparse.ArgumentParser) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("ERROR record 需要一个命令：agenttest record <dir> -- <command>", file=sys.stderr)
        return EXIT_FAIL
    if args.repeat < 1:
        print("ERROR --repeat 至少是 1", file=sys.stderr)
        return EXIT_FAIL
    if args.repeat == 1:
        return _record_once(args, command)
    return _record_batch(args, command)


def _record_once(args, command: list) -> int:
    try:
        outcome = record(args.target, command)
    except (RecordError, CassetteError, ProcessError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    print(record_summary(outcome))
    if not args.asserts:
        return EXIT_OK
    results = asrt.evaluate_all(args.asserts, outcome.events)
    for result in results:
        print("  PASS      " + result.expr if result.ok else "  " + result.message)
    return EXIT_OK if all(result.ok for result in results) else EXIT_FAIL


def _record_batch(args, command: list) -> int:
    target = Path(args.target)
    runs_root = target / "runs"
    summaries = []
    for index in range(1, args.repeat + 1):
        try:
            outcome = record(runs_root / ("run-" + str(index)), command)
        except (RecordError, CassetteError, ProcessError) as exc:
            print(
                "ERROR 第 "
                + str(index)
                + "/"
                + str(args.repeat)
                + " 次运行录制失败："
                + str(exc),
                file=sys.stderr,
            )
            return EXIT_FAIL
        summary = st.summarize_run(outcome.events, args.asserts, index=index)
        summaries.append(summary)
        print(
            "  run {}/{}  {}  tokens {:,} · 耗时 {:.3f}s · 工具调用 {}".format(
                index,
                args.repeat,
                "OK  " if summary["ok"] else "FAIL",
                summary["tokens"],
                summary["duration"],
                summary["tool_calls"],
            )
        )
        for message in summary["failures"]:
            print("    " + message)
    try:
        path = st.write_batch(target, summaries)
    except OSError as exc:
        print("ERROR 写不出 batch 文件：" + str(exc), file=sys.stderr)
        return EXIT_FAIL
    stats = st.summarize_batch(summaries)
    print("recorded {} runs -> {}".format(args.repeat, path))
    print(
        "  成功 {}/{} · tokens 平均 {:,.0f} · 耗时平均 {:.3f}s · 工具调用平均 {:.1f}".format(
            stats.successes,
            stats.runs,
            stats.mean_tokens,
            stats.mean_duration,
            stats.mean_tool_calls,
        )
    )
    note = st.confidence_note(stats)
    if note:
        print(note)
    print("下一步：agenttest stat " + str(path) + ' --assert "success>=0.8"')
    return EXIT_OK


def _cmd_replay(args, parser: argparse.ArgumentParser) -> int:
    for expr in args.asserts:
        try:
            asrt.evaluate(expr, [])
        except asrt.AssertionError_ as exc:
            print("ERROR 断言写法不对：" + str(exc), file=sys.stderr)
            return EXIT_FAIL
        except Exception:
            pass  # 表达式本身合法，只是没有事件可判
    try:
        outcome = replay(args.target, args.asserts)
    except (ReplayError, CassetteError, ProcessError) as exc:
        print("ERROR replay 失败：" + str(exc), file=sys.stderr)
        return EXIT_FAIL

    path = cassette_path(args.target)
    start = dict(outcome.recorded[0])
    print("replay " + str(args.target))
    print(
        "  cassette  "
        + str(len(outcome.recorded))
        + " 条记录，sha256 哈希链完整（"
        + path.name
        + "）"
    )
    print("  agent     " + " ".join(str(a) for a in start.get("argv") or []))
    print("  事件      " + str(len(outcome.events)) + " 条，与 cassette 完全一致")
    changed = ", ".join(dict(outcome.recorded[-1]).get("files_changed") or []) or "（无）"
    print("  产物      " + changed + " 与记录一致")
    for result in outcome.results:
        if result.ok:
            print("  PASS      " + result.expr)
        else:
            print("  " + result.message)
    if outcome.ok:
        total = len(outcome.results)
        print("PASS " + str(args.target) + "  (" + str(total) + " 个断言全部通过)")
        return EXIT_OK
    print(
        "FAILED "
        + str(args.target)
        + "  ("
        + str(len(outcome.failed))
        + "/"
        + str(len(outcome.results))
        + " 条断言失败)"
    )
    return EXIT_FAIL


def _cmd_diff(args) -> int:
    try:
        before = read_cassette(args.before)
        after = read_cassette(args.after)
    except CassetteError as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    print(diff_runs(before, after, str(args.before), str(args.after)))
    return EXIT_OK


def _cmd_stat(args) -> int:
    try:
        summaries = st.read_batch(args.path)
        stats = st.summarize_batch(summaries)
        assertions = [st.parse_stat_assertion(expr) for expr in args.asserts]
    except (st.StatError, CassetteError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    results = [st.evaluate_stat(assertion, stats) for assertion in assertions]
    label = str(st.batch_path(args.path))
    print(st.format_report(label, stats, results))
    if all(result.ok for result in results):
        print("PASS " + label + " (" + str(len(results)) + " 条统计断言通过)")
        return EXIT_OK
    failed = sum(1 for result in results if not result.ok)
    print("FAILED " + label + " (" + str(failed) + "/" + str(len(results)) + " 条统计断言失败)")
    return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
