"""CLI：三个动词 record / replay / diff（argparse，不引第三方库）。"""

from __future__ import annotations

import argparse
import sys

from . import assertions as asrt
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
        description="把 agent 的行为当代码来测：record / replay / diff",
    )
    subs = parser.add_subparsers(dest="verb", required=True)

    rec = subs.add_parser("record", help="跑一次 agent，把事件流落成 cassette")
    rec.add_argument("target", help="cassette 目录，例如 examples/good")
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
    parser.error("未知子命令：" + str(args.verb))
    return EXIT_FAIL


def _cmd_record(args, parser: argparse.ArgumentParser) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("ERROR record 需要一个命令：agenttest record <dir> -- <command>", file=sys.stderr)
        return EXIT_FAIL
    try:
        outcome = record(args.target, command)
    except (RecordError, CassetteError, ProcessError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    print(record_summary(outcome))
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


if __name__ == "__main__":
    raise SystemExit(main())
