"""CLI：record / record-subprocess / replay / diff / stat / import（argparse，不引第三方库）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import adapters
from . import assertions as asrt
from . import flaky as fk
from . import regress as rg
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
        description="把 agent 的行为当代码来测：record / record-subprocess / replay / diff / stat / import",
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

    rsp = subs.add_parser(
        "record-subprocess",
        help="录制一个真实 CLI agent 的一次运行（只记进程层能观测到的东西）",
        description=(
            "录制一个真实 CLI agent 的一次运行。要跑的命令写在 -- 之后："
            "agenttest record-subprocess <dir> [选项] -- <命令>。"
            "选项放在 -- 前后都行。"
        ),
    )
    rsp.add_argument("target", help="cassette 目录，例如 cassettes/run1")
    rsp.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="超过这个秒数就杀掉子进程并报错（默认不设上限）",
    )
    rsp.add_argument(
        "--stream-limit",
        type=int,
        default=adapters.DEFAULT_STREAM_LIMIT,
        metavar="N",
        help="stdout / stderr 各保留多少字符（默认 %(default)s）",
    )
    rsp.add_argument("--cwd", default=None, help="子进程的工作目录（默认当前目录）")
    rsp.add_argument(
        "--watch",
        default=None,
        help="比较文件改动的工作目录（默认等于 --cwd）",
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
    sta.add_argument(
        "--point-estimate",
        action="store_true",
        help="比例断言只按点估计判定（非统计显著；默认要求 95%% 置信区间也过线）",
    )

    reg = subs.add_parser("regress", help="多次运行的回归看板：汇总断言 + 与基线比对")
    reg.add_argument("path", help="装着多份 cassette 的目录，或单个 cassette.jsonl")
    reg.add_argument(
        "--assert",
        dest="asserts",
        action="append",
        default=[],
        metavar="EXPR",
        help="断言，可重复：before:quote_error / touched:src/auth.py / exit:0 ...",
    )
    reg.add_argument(
        "--baseline",
        default=None,
        metavar="REPORT.json",
        help="上一份 report.json：给了就做基线比对（新增失败 / 修好 / 通过率 / 成本）",
    )
    reg.add_argument(
        "--out",
        default=None,
        metavar="DIR|FILE",
        help="报告写到哪里：目录则写 <DIR>/report.json，以 .json 结尾则写那个文件",
    )
    reg.add_argument(
        "--html",
        action="store_true",
        help="额外生成单文件 index.html（零外部依赖、无 CDN，可离线打开）",
    )
    reg.add_argument(
        "--fail-on",
        dest="fail_on",
        default="newly_failing",
        choices=rg.FAIL_ON_CHOICES,
        help="退出码策略（默认 %(default)s）：newly_failing / any / never",
    )

    flk = subs.add_parser(
        "flaky", help="多次运行的抖动识别：这条断言到底稳不稳，够不够格判断退步"
    )
    flk.add_argument(
        "paths",
        nargs="+",
        metavar="runs",
        help="一个或多个 cassette 目录（<dir>/cassette.jsonl 或 <dir>/<run>/cassette.jsonl）",
    )
    flk.add_argument(
        "--assert",
        dest="asserts",
        action="append",
        default=[],
        metavar="EXPR",
        help="断言，可重复：before:quote_error / touched:src/auth.py / exit:0 ...",
    )
    flk.add_argument(
        "--min-runs",
        dest="min_runs",
        type=int,
        default=fk.MIN_RUNS,
        metavar="N",
        help="少于这个运行数就整表标 UNRELIABLE、不给判定（默认 %(default)s）",
    )
    flk.add_argument(
        "--out",
        default=None,
        metavar="REPORT.json",
        help="把判定结果写成 JSON（schema_version / generated_at / 每条断言的 runs·passed·pass_rate·low·high·verdict）",
    )
    flk.add_argument(
        "--fail-on",
        dest="fail_on",
        default="never",
        choices=["never", "flaky"],
        help="退出码策略（默认 %(default)s，只报告不拦人）",
    )

    subs.add_parser("demo", help="一条命令自证：record → replay PASS/FAIL → diff → 回归报告")
    imp = subs.add_parser("import", help="把已有的模型日志导入成 cassette")
    imp.add_argument("source", help="日志文件（.jsonl 或 .json）")
    imp.add_argument("outdir", help="输出目录，写成 <outdir>/cassette.jsonl")
    imp.add_argument(
        "--format",
        dest="fmt",
        default="auto",
        choices=["auto", "openai", "anthropic"],
        help="输入格式；默认 auto 自动识别",
    )
    imp.add_argument(
        "--exit-code",
        dest="exit_code",
        type=int,
        default=None,
        help="日志里没有退出码时写入的值（默认 0）",
    )
    return parser


def _split_command(argv: list) -> tuple:
    """把 record-subprocess 的 "--" 之后的部分单独摘出来。

    argparse 的 REMAINDER 会把 target 之后的选项也吞进 command（
    "record-subprocess DIR --cwd . -- cmd" 会变成 command=['--cwd', ...]）。
    这里先按第一个 "--" 切开，选项就写在哪儿都行了。
    """
    if not argv or argv[0] != "record-subprocess" or "--" not in argv:
        return list(argv), None
    cut = argv.index("--")
    return list(argv[:cut]), list(argv[cut + 1:])


def main(argv: list | None = None) -> int:
    _force_utf8()
    raw, tail = _split_command(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(raw)
    if args.verb == "record":
        return _cmd_record(args, parser)
    if args.verb == "record-subprocess":
        args.command = list(tail) if tail is not None else []
        return _cmd_record_subprocess(args)
    if args.verb == "replay":
        return _cmd_replay(args, parser)
    if args.verb == "diff":
        return _cmd_diff(args)
    if args.verb == "stat":
        return _cmd_stat(args)
    if args.verb == "regress":
        return _cmd_regress(args)
    if args.verb == "flaky":
        return _cmd_flaky(args)
    if args.verb == "demo":
        from .demo import run_demo

        return run_demo()
    if args.verb == "import":
        return _cmd_import(args)
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


def _cmd_record_subprocess(args) -> int:
    """跑一个真实 CLI agent 并录下来：只记观测到的，缺的写进 meta.unobserved。"""
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print(
            "ERROR record-subprocess 需要一个命令："
            "agenttest record-subprocess <dir> -- <command>",
            file=sys.stderr,
        )
        return EXIT_FAIL
    try:
        outcome = adapters.record_subprocess(
            command,
            args.target,
            cwd=args.cwd,
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            watch=args.watch,
        )
    except (adapters.AdapterError, CassetteError, OSError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    print(adapters.summarize(outcome))
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
    point_estimate = bool(getattr(args, "point_estimate", False))
    results = [
        st.evaluate_stat(assertion, stats, point_estimate) for assertion in assertions
    ]
    label = str(st.batch_path(args.path))
    print(st.format_report(label, stats, results, point_estimate))
    if all(result.ok for result in results):
        print("PASS " + label + " (" + str(len(results)) + " 条统计断言通过)")
        return EXIT_OK
    failed = sum(1 for result in results if not result.ok)
    print("FAILED " + label + " (" + str(failed) + "/" + str(len(results)) + " 条统计断言失败)")
    return EXIT_FAIL


def _cmd_regress(args) -> int:
    try:
        report = rg.regress(
            args.path,
            asserts=args.asserts,
            baseline=args.baseline,
            out=args.out,
            html=args.html,
        )
    except (rg.RegressError, CassetteError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    print(rg.render_table(report))
    for kind, location in report.written.items():
        print("  报告        " + kind + " -> " + location)
    code = rg.resolve_exit_code(report, args.fail_on)
    if report.errored:
        reason = "有 cassette 读不了"
    elif report.comparison and report.comparison.newly_failing:
        reason = "新增失败 " + str(len(report.comparison.newly_failing)) + " 条"
    elif report.passed_runs == 0:
        reason = "所有 run 都失败"
    else:
        reason = "没有退步"
    print("门禁 fail-on=" + args.fail_on + " → exit " + str(code) + "（" + reason + "）")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

def _cmd_import(args) -> int:
    """把已有的模型日志映射成 cassette：只做映射，不假装能重放。"""
    from .importers import ImporterError, load

    fmt = None if args.fmt in (None, "auto") else args.fmt
    try:
        cassette = load(args.source, format=fmt, exit_code=args.exit_code)
    except ImporterError as exc:
        print("ERROR 导入失败：" + str(exc))
        return 1

    path = cassette.write(args.outdir)
    counts = cassette.counts
    print("import " + str(args.source))
    print("  格式    " + (cassette.format or "?"))
    print("  事件    " + str(len(cassette.events)) + " 条 " + str(counts))
    if cassette.synthetic_timestamps:
        print("  时间戳  日志里缺时间戳，已按顺序合成（meta.synthetic_timestamps = true，不是真实耗时）")
    else:
        print("  时间戳  来自日志的真实值")
    print(
        "  warnings " + str(len(cassette.warnings)) + " 条"
        + ("，见 run.start.meta.warnings" if cassette.warnings else "")
    )
    print("  写出    " + str(path))
    print(
        "注意 导入的 cassette 不能 replay（日志里没有可重跑的 agent），"
        "但可以 diff、跑断言、归档。"
    )


def _cmd_flaky(args) -> int:
    try:
        report = fk.collect(args.paths, args.asserts, min_runs=args.min_runs)
    except (fk.FlakyError, rg.RegressError, CassetteError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return EXIT_FAIL
    print(fk.render_table(report))
    if args.out:
        path = Path(args.out)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            path.write_bytes((payload + "\n").encode("utf-8"))
        except OSError as exc:
            print("ERROR 写不出 --out 文件：" + str(exc), file=sys.stderr)
            return EXIT_FAIL
        print("  报告        json -> " + str(path))
    code = fk.gate_exit_code(report, args.fail_on)
    if args.fail_on == "never":
        reason = "只报告，不拦人"
    elif report.noisy:
        reason = "观察到 " + str(len(report.noisy)) + " 条断言时过时不过"
    else:
        reason = "没有观察到抖动"
    print("门禁 fail-on=" + args.fail_on + " → exit " + str(code) + "（" + reason + "）")
    return code
    return 0