"""多次运行的回归看板（v0.3）。

一次 replay 只证明"这一次的行为"；agent 是不确定的，所以要跑 N 次、存成基线，
下次改 prompt / 换模型后自动比对：谁退步了，一眼看见。

    report = regress("runs/", asserts=["before:quote_error"])
    report = regress("runs-new/", asserts=[...], baseline="baseline.json", out="report/")
    print(render_table(report))

判定语义全部复用 assertions / events，这里只做汇总与比对，不另造一套。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Iterable

from . import assertions as asrt
from . import events as ev
from .cassette import CASSETTE_NAME, CassetteError, read_cassette

REPORT_NAME = "report.json"
HTML_NAME = "index.html"
FAIL_ON_CHOICES = ("newly_failing", "any", "never")
MAX_RUNS = 500

# assertions 的失败文案里本来就带"第 N 个事件"，这里只是把它取出来单独展示。
_EVENT_INDEX = re.compile(r"第 (\d+) 个事件")


class RegressError(RuntimeError):
    """regress 跑不起来：找不到 cassette、断言写错、参数非法。"""


# -- 数据结构 -----------------------------------------------------------
@dataclass
class Failure:
    expr: str
    message: str
    event_index: int | None = None

    @classmethod
    def from_result(cls, result: asrt.AssertionResult) -> "Failure":
        match = _EVENT_INDEX.search(result.message)
        return cls(
            expr=result.expr,
            message=result.message,
            event_index=int(match.group(1)) if match else None,
        )

    def to_dict(self) -> dict:
        return {"expr": self.expr, "message": self.message, "event_index": self.event_index}


@dataclass
class RunResult:
    run_id: str
    path: str
    passed: bool = False
    exit_code: int | None = None
    tokens: int = 0
    duration: float = 0.0
    tool_calls: int = 0
    assertions: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "path": self.path,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "tokens": self.tokens,
            "duration": self.duration,
            "tool_calls": self.tool_calls,
            "error": self.error,
            "assertions": [
                {"expr": a.expr if hasattr(a, "expr") else a["expr"],
                 "ok": a.ok if hasattr(a, "ok") else a["ok"],
                 "message": a.message if hasattr(a, "message") else a["message"]}
                for a in self.assertions
            ],
            "failures": [f.to_dict() for f in self.failures],
        }


@dataclass
class Comparison:
    newly_failing: list = field(default_factory=list)
    newly_failing_noisy: list = field(default_factory=list)
    unmatched_asserts: list = field(default_factory=list)
    fixed: list = field(default_factory=list)
    pass_rate_before: float = 0.0
    pass_rate_after: float = 0.0
    cost: dict = field(default_factory=dict)
    baseline_runs: int = 0
    missing_runs: list = field(default_factory=list)

    @property
    def pass_rate_delta(self) -> float:
        return self.pass_rate_after - self.pass_rate_before

    def to_dict(self) -> dict:
        return {
            "newly_failing": self.newly_failing,
            "newly_failing_noisy": self.newly_failing_noisy,
            "unmatched_asserts": self.unmatched_asserts,
            "fixed": self.fixed,
            "pass_rate": {
                "before": self.pass_rate_before,
                "after": self.pass_rate_after,
                "delta": round(self.pass_rate_delta, 4),
            },
            "cost": self.cost,
            "baseline_runs": self.baseline_runs,
            "missing_runs": self.missing_runs,
        }


@dataclass
class Report:
    root: str
    asserts: list = field(default_factory=list)
    runs: list = field(default_factory=list)
    comparison: Comparison | None = None
    generated_at: str = ""
    written: dict = field(default_factory=dict)

    @property
    def passed_runs(self) -> int:
        return sum(1 for run in self.runs if run.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed_runs / len(self.runs) if self.runs else 0.0

    @property
    def errored(self) -> list:
        return [run for run in self.runs if run.error]

    @property
    def failures(self) -> list:
        return [(run, failure) for run in self.runs for failure in run.failures]

    def to_dict(self) -> dict:
        return {
            "version": "0.3",
            "generated_at": self.generated_at,
            "root": self.root,
            "asserts": list(self.asserts),
            "summary": {
                "runs": len(self.runs),
                "passed": self.passed_runs,
                "pass_rate": round(self.pass_rate, 4),
                "errored": len(self.errored),
            },
            "runs": [run.to_dict() for run in self.runs],
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


# -- 发现要跑的 run -----------------------------------------------------
def discover_runs(target: str | Path) -> list:
    """把目录里的所有 cassette 找出来，返回 [(run_id, cassette 路径)]。"""
    path = Path(target)
    if not path.exists():
        raise RegressError(
            f"路径不存在：{path}。先用 agenttest record <dir> 录一份，"
            "或者确认 runs/ 是不是放错了目录"
        )
    if path.is_file():
        if path.suffix.lower() != ".jsonl":
            raise RegressError(
                f"{path} 不是 cassette：要一份 cassette.jsonl，或者一个装着多份 cassette 的目录"
            )
        return [(path.stem, path)]

    found = []
    for cassette in sorted(path.rglob(CASSETTE_NAME)):
        relative = cassette.parent.relative_to(path)
        parts = relative.parts
        if any(part.startswith(".") for part in parts) or len(parts) > 3:
            continue  # 跳过 .git / .work 之类的痕迹目录，别把临时产物当 run
        run_id = "." if str(relative) == "." else relative.as_posix()
        if run_id == ".":
            run_id = path.name
        found.append((run_id, cassette))
    if not found:
        raise RegressError(
            f"{path} 里没找到任何 {CASSETTE_NAME}：空目录？cassette 要放在 "
            f"<dir>/{CASSETTE_NAME} 或 <dir>/<run>/{CASSETTE_NAME}"
        )
    if len(found) > MAX_RUNS:
        raise RegressError(f"{path} 里有 {len(found)} 份 cassette，超过上限 {MAX_RUNS}，先缩小范围")
    return found


# -- 单次运行 -----------------------------------------------------------
def summarize_run(run_id: str, cassette: Path, asserts: Iterable[str]) -> RunResult:
    run = RunResult(run_id=run_id, path=str(cassette))
    try:
        events = read_cassette(cassette)
    except CassetteError as exc:
        run.error = str(exc)
        return run
    run.exit_code = ev.run_end(events).get("exit_code") if ev.of_type(events, "run.end") else None
    usage_in = sum(int((e.get("usage") or {}).get("in", 0) or 0)
                   for e in events if e.get("type") == "model.result")
    usage_out = sum(int((e.get("usage") or {}).get("out", 0) or 0)
                    for e in events if e.get("type") == "model.result")
    run.tokens = usage_in + usage_out
    run.tool_calls = len(ev.tool_calls(events))
    if ev.of_type(events, "run.start") and ev.of_type(events, "run.end"):
        run.duration = round(
            float(ev.run_end(events).get("t", 0.0))
            - float(ev.run_start(events).get("t", 0.0)),
            4,
        )
    for expr in asserts:
        try:
            result = asrt.evaluate(expr, events)
        except Exception as exc:  # 例如没有 run.end 却断言 exit:0
            result = asrt.AssertionResult(expr=expr, ok=False, message=f"FAIL {expr} — 无法判定：{exc}")
        run.assertions.append(result)
        if not result.ok:
            run.failures.append(Failure.from_result(result))
    run.passed = not run.failures and run.error is None
    return run


def check_assertions(asserts: Iterable[str]) -> None:
    for expr in asserts:
        try:
            asrt.evaluate(expr, [])
        except asrt.AssertionError_ as exc:
            raise RegressError(f"断言写法不对（{expr!r}）：{exc}") from exc
        except Exception:
            pass  # 表达式合法，只是空事件流判不出来


# -- 基线比对 -----------------------------------------------------------
def _assert_map(report: Report) -> dict:
    marks = {}
    for run in report.runs:
        for result in run.assertions:
            expr = result.expr if hasattr(result, "expr") else result["expr"]
            ok = result.ok if hasattr(result, "ok") else result["ok"]
            marks[(run.run_id, expr)] = ok
    return marks


def _mean(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


def _delta(before: float, after: float) -> dict:
    percent = None if before == 0 else round((after - before) / before * 100, 1)
    return {"before": round(before, 4), "after": round(after, 4), "delta": round(after - before, 4), "percent": percent}


def load_flaky_report(source) -> dict:
    """读 flaky --out 的 JSON，返回 {断言原文: 判定}。"""
    import json

    path = Path(source)
    if not path.exists():
        raise RegressError("flaky 报告不存在：" + str(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise RegressError("flaky 报告不是合法 JSON：" + str(exc)) from exc
    items = data.get("asserts") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RegressError("flaky 报告缺 asserts 数组：确认它来自 agenttest flaky --out")
    return {str(item.get("expr") or ""): str(item.get("verdict") or "") for item in items}


def noise_only(flaky_map: dict) -> set:
    """只有 MIXED_OBSERVED 算噪声；INSUFFICIENT_RUNS 证据不足，不能当噪声排除。"""
    return {expr for expr, verdict in flaky_map.items() if verdict == "MIXED_OBSERVED"}


def compare(baseline: Report, current: Report, noise: set | None = None) -> Comparison:
    before = _assert_map(baseline)
    comparison = Comparison(
        pass_rate_before=baseline.pass_rate,
        pass_rate_after=current.pass_rate,
        baseline_runs=len(baseline.runs),
    )
    current_runs = {run.run_id for run in current.runs}
    comparison.missing_runs = [run.run_id for run in baseline.runs if run.run_id not in current_runs]
    for run in current.runs:
        for result in run.assertions:
            key = (run.run_id, result.expr)
            if key not in before:
                continue  # 基线里没有这条：是新增的 run/断言，不算退步
            if before[key] and not result.ok:
                failure = next((f for f in run.failures if f.expr == result.expr), None)
                item = {
                    "run_id": run.run_id,
                    "expr": result.expr,
                    "event_index": failure.event_index if failure else None,
                    "message": result.message,
                }
                if noise and result.expr in noise:
                    comparison.newly_failing_noisy.append(item)
                else:
                    comparison.newly_failing.append(item)
                    if noise and result.expr not in noise:
                        comparison.unmatched_asserts.append(result.expr)
            elif not before[key] and result.ok:
                comparison.fixed.append({"run_id": run.run_id, "expr": result.expr})
    comparison.cost = {
        "tokens": _delta(_mean([r.tokens for r in baseline.runs]), _mean([r.tokens for r in current.runs])),
        "duration": _delta(
            _mean([r.duration for r in baseline.runs]), _mean([r.duration for r in current.runs])
        ),
        "tool_calls": _delta(
            _mean([r.tool_calls for r in baseline.runs]), _mean([r.tool_calls for r in current.runs])
        ),
    }
    return comparison


def load_report(source) -> Report:
    if isinstance(source, Report):
        return source
    if isinstance(source, dict):
        data = source
    else:
        path = Path(source)
        if not path.exists():
            raise RegressError(f"找不到基线文件：{path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            raise RegressError(f"基线文件不是合法 JSON：{path}（{exc}）") from exc
    if not isinstance(data, dict) or "runs" not in data:
        raise RegressError("基线文件缺少 runs 字段，不像 agenttest regress 产出的 report.json")
    assertions_by_run = {}
    runs = []
    for item in data.get("runs", []):
        run_assertions = []
        for entry in item.get("assertions") or []:
            run_assertions.append(
                asrt.AssertionResult(
                    expr=entry.get("expr", ""),
                    ok=bool(entry.get("ok")),
                    message=entry.get("message", ""),
                )
            )
        assertions_by_run[item.get("run_id")] = run_assertions
        runs.append(
            RunResult(
                run_id=item.get("run_id", "?"),
                path=item.get("path", ""),
                passed=bool(item.get("passed")),
                exit_code=item.get("exit_code"),
                tokens=int(item.get("tokens", 0) or 0),
                duration=float(item.get("duration", 0.0) or 0.0),
                tool_calls=int(item.get("tool_calls", 0) or 0),
                assertions=run_assertions,
                failures=[
                    Failure(
                        expr=f.get("expr", ""),
                        message=f.get("message", ""),
                        event_index=f.get("event_index"),
                    )
                    for f in item.get("failures") or []
                ],
                error=item.get("error"),
            )
        )
    return Report(
        root=data.get("root", ""),
        asserts=list(data.get("asserts") or []),
        runs=runs,
        generated_at=data.get("generated_at", ""),
    )


# -- 主入口 -------------------------------------------------------------
def regress(
    cassettes_or_dir,
    asserts: Iterable[str] = (),
    baseline=None,
    out=None,
    html: bool = False,
    flaky_report=None,
) -> Report:
    """跑一遍看板：汇总每个 run 的断言结果，可选与基线比对，可选落盘。"""
    asserts = list(asserts)
    check_assertions(asserts)
    runs = [summarize_run(run_id, cassette, asserts) for run_id, cassette in discover_runs(cassettes_or_dir)]
    report = Report(
        root=str(cassettes_or_dir),
        asserts=asserts,
        runs=runs,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    noise = set()
    if flaky_report is not None:
        noise = noise_only(load_flaky_report(flaky_report))
    if baseline is not None:
        report.comparison = compare(load_report(baseline), report, noise=noise)
    if out is not None:
        report.written = write_outputs(report, out, html=html)
    return report


def write_outputs(report: Report, out, html: bool = False) -> dict:
    """把 report 落盘；--html 时同时产出单文件 index.html。"""
    out_path = Path(out)
    if out_path.suffix.lower() == ".json":
        json_path = out_path
        html_dir = out_path.parent
    else:
        json_path = out_path / REPORT_NAME
        html_dir = out_path
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_bytes(
        (json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    written = {"report": str(json_path)}
    if html:
        html_path = html_dir / HTML_NAME
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_bytes(render_html(report).encode("utf-8"))
        written["html"] = str(html_path)
    return written


# -- 终端表格 -----------------------------------------------------------
def _display_width(text: str) -> int:
    """中日韩字符占两格：表格对齐不能只数 len。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _short_event(run: RunResult) -> str:
    for failure in run.failures:
        if failure.event_index is not None:
            return f"第{failure.event_index}事件"
    return ""


def render_table(report: Report) -> str:
    lines = []
    lines.append(
        f"regress {report.root} — {len(report.runs)} 次运行，{len(report.asserts)} 条断言"
    )
    header = ["run", *report.asserts, "tokens", "耗时", "工具", "结果"]
    rows = [header]
    for run in report.runs:
        cells = [run.run_id]
        marks = {result.expr: result for result in run.assertions}
        for expr in report.asserts:
            result = marks.get(expr)
            if result is None:  # cassette 读不了，这条断言没判
                cells.append("—")
            elif result.ok:
                cells.append("PASS")
            else:
                hint = _short_event(run)
                cells.append("FAIL" + (f"({hint})" if hint else ""))
        cells.append(f"{run.tokens:,}")
        cells.append(f"{run.duration:.3f}s")
        cells.append(str(run.tool_calls))
        cells.append("ERROR" if run.error else ("PASS" if run.passed else "FAIL"))
        rows.append(cells)
    widths = [
        max(_display_width(row[index]) for row in rows) for index in range(len(header))
    ]
    for index, row in enumerate(rows):
        if index == 1:
            lines.append("  " + "  ".join("-" * width for width in widths))
        lines.append("  " + "  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)).rstrip())
    lines.append(
        f"  通过率      {report.passed_runs}/{len(report.runs)}"
        f"（{report.pass_rate * 100:.0f}%）"
    )
    for run in report.errored:
        lines.append(f"  ERROR       {run.run_id}：{run.error}")
    for run, failure in report.failures:
        where = f"第 {failure.event_index} 个事件" if failure.event_index else "未定位到事件"
        lines.append(f"  FAIL        {run.run_id} / {failure.expr} — {where}")
        lines.append(f"              {failure.message}")
    if report.comparison:
        lines.append("")
        lines.extend(render_comparison(report.comparison))
    return "\n".join(lines)


def render_comparison(comparison: Comparison) -> str:
    lines = [f"基线比对（基线 {comparison.baseline_runs} 次运行 → 现在）"]
    if comparison.newly_failing:
        lines.append(f"  新增失败    {len(comparison.newly_failing)} 条")
        for item in comparison.newly_failing:
            where = (
                f"第一次失败在第 {item['event_index']} 个事件"
                if item.get("event_index")
                else "失败事件未定位"
            )
            lines.append(f"    - {item['run_id']} / {item['expr']}（{where}）")
    else:
        lines.append("  新增失败    0 条")
    noisy = getattr(comparison, "newly_failing_noisy", [])
    if noisy:
        lines.append(f"  噪声失败    {len(noisy)} 条（已知不稳定，不计入退步）")
        for item in noisy:
            where = (
                f"第 {item['event_index']} 个事件"
                if item.get("event_index")
                else "失败事件未定位"
            )
            lines.append(f"    ~ {item['run_id']} / {item['expr']}（{where}）")
        if not comparison.newly_failing:
            lines.append(
                "  注意        本次失败全部来自已知不稳定断言（MIXED_OBSERVED），未阻止 CI —— "
                "它们被分栏而不是被隐藏"
            )
    if comparison.fixed:
        lines.append(f"  修好        {len(comparison.fixed)} 条")
        for item in comparison.fixed:
            lines.append(f"    + {item['run_id']} / {item['expr']}")
    else:
        lines.append("  修好        0 条")
    lines.append(
        "  通过率      {:.0f}% → {:.0f}%（{:+.0f} 个百分点）".format(
            comparison.pass_rate_before * 100,
            comparison.pass_rate_after * 100,
            comparison.pass_rate_delta * 100,
        )
    )
    def _fmt(name: str, value: float) -> str:
        return f"{value:.3f}s" if name == "duration" else f"{value:,.0f}"

    parts = []
    for name, label in (("tokens", "tokens"), ("duration", "耗时"), ("tool_calls", "工具调用")):
        item = comparison.cost.get(name) or {}
        before, after, percent = item.get("before", 0), item.get("after", 0), item.get("percent")
        change = "n/a" if percent is None else f"{percent:+.0f}%"
        parts.append(f"{label} {_fmt(name, before)} → {_fmt(name, after)} ({change})")
    lines.append("  成本        " + " · ".join(parts))
    if comparison.missing_runs:
        lines.append("  基线里有、这次没有的 run：" + ", ".join(comparison.missing_runs))
    return lines


# -- 退出码策略 ---------------------------------------------------------
def resolve_exit_code(report: Report, fail_on: str = "newly_failing") -> int:
    if fail_on not in FAIL_ON_CHOICES:
        raise RegressError(f"--fail-on 只支持 {'/'.join(FAIL_ON_CHOICES)}，收到 {fail_on!r}")
    if report.errored:
        return 1  # 有 cassette 读不了：无论如何都算失败
    if fail_on == "never":
        return 0
    if fail_on == "any":
        return 0 if report.passed_runs == len(report.runs) else 1
    newly = bool(report.comparison and report.comparison.newly_failing)
    all_failed = bool(report.runs) and report.passed_runs == 0
    return 1 if (newly or all_failed) else 0


# -- HTML（单文件、无 CDN、无 JS） ---------------------------------------
_CSS = """
body { font: 14px/1.5 -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
       margin: 2rem; color: #1f2328; background: #fff; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
h2 { font-size: 1.05rem; margin: 2rem 0 .5rem; }
.meta { color: #656d76; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin-bottom: .5rem; }
th, td { border: 1px solid #d0d7de; padding: .35rem .6rem; text-align: left; }
th { background: #f6f8fa; font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.pass { color: #1a7f37; font-weight: 600; }
.fail { color: #cf222e; font-weight: 600; }
.err { color: #9a6700; font-weight: 600; }
.failrow { background: #fff5f5; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; padding: .75rem;
      white-space: pre-wrap; word-break: break-word; margin: .25rem 0 1rem; }
ul { margin: .25rem 0 1rem 1.2rem; padding: 0; }
"""


def render_html(report: Report) -> str:
    def cell(ok: bool, text: str = "") -> str:
        word = "PASS" if ok else "FAIL"
        return f'<td class="{ "pass" if ok else "fail" }">{word}{escape(text)}</td>'

    rows = []
    for run in report.runs:
        status = "ERROR" if run.error else ("PASS" if run.passed else "FAIL")
        status_class = "err" if run.error else ("pass" if run.passed else "fail")
        cells = [f"<td>{escape(run.run_id)}</td>"]
        marks = {result.expr: result for result in run.assertions}
        for expr in report.asserts:
            result = marks.get(expr)
            if result is None:
                cells.append('<td class="err">—</td>')
            else:
                cells.append(cell(result.ok))
        cells.append(f'<td class="num">{run.tokens:,}</td>')
        cells.append(f'<td class="num">{run.duration:.3f}s</td>')
        cells.append(f'<td class="num">{run.tool_calls}</td>')
        cells.append(f'<td class="{status_class}">{status}</td>')
        row_class = ' class="failrow"' if not run.passed else ""
        rows.append(f"  <tr{row_class}>" + "".join(cells) + "</tr>")

    header = "".join(
        f"<th>{escape(name)}</th>" for name in ("run", *report.asserts, "tokens", "耗时", "工具调用", "结果")
    )

    failures_html = []
    for run, failure in report.failures:
        where = f"第 {failure.event_index} 个事件" if failure.event_index else "未定位到事件"
        failures_html.append(
            f"    <li><strong>{escape(run.run_id)}</strong> / <code>{escape(failure.expr)}</code>"
            f" — {escape(where)}<pre>{escape(failure.message)}</pre></li>"
        )
    for run in report.errored:
        failures_html.append(
            f"    <li><strong>{escape(run.run_id)}</strong> — cassette 读不了"
            f"<pre>{escape(run.error or '')}</pre></li>"
        )

    comparison_html = ""
    if report.comparison:
        items = []
        noisy = getattr(report.comparison, "newly_failing_noisy", []) if report.comparison else []
        if noisy:
            items.append("<h2>噪声失败（已知不稳定，不计入退步）</h2><ul>")
            for item in noisy:
                where = (
                    f"第 {item['event_index']} 个事件"
                    if item.get("event_index")
                    else "失败事件未定位"
                )
                items.append(
                    f"    <li><strong>{escape(str(item.get('run_id')))}</strong> / "
                    f"<code>{escape(str(item.get('expr')))}</code> — {escape(where)}</li>"
                )
            items.append("</ul>")
        if report.comparison.newly_failing:
            items.append("<h2>新增失败（退步）</h2><ul>")
            for item in report.comparison.newly_failing:
                where = (
                    f"第一次失败在第 {item['event_index']} 个事件"
                    if item.get("event_index")
                    else "失败事件未定位"
                )
                items.append(
                    f"    <li><strong>{escape(item['run_id'])}</strong> / "
                    f"<code>{escape(item['expr'])}</code> — {escape(where)}"
                    f"<pre>{escape(item.get('message') or '')}</pre></li>"
                )
            items.append("</ul>")
        else:
            items.append("<h2>新增失败（退步）</h2><p>无</p>")
        if report.comparison.fixed:
            items.append("<h2>修好</h2><ul>")
            for item in report.comparison.fixed:
                items.append(
                    f"    <li><strong>{escape(item['run_id'])}</strong> / "
                    f"<code>{escape(item['expr'])}</code></li>"
                )
            items.append("</ul>")
        else:
            items.append("<h2>修好</h2><p>无</p>")
        cost = report.comparison.cost or {}
        cost_rows = []
        for key, label in (("tokens", "tokens"), ("duration", "耗时"), ("tool_calls", "工具调用")):
            item = cost.get(key) or {}
            percent = item.get("percent")
            change = "n/a" if percent is None else f"{percent:+.0f}%"
            cost_rows.append(
                f"    <tr><td>{escape(label)}</td>"
                f'<td class="num">{item.get("before", 0):,.0f}</td>'
                f'<td class="num">{item.get("after", 0):,.0f}</td>'
                f'<td class="num">{escape(change)}</td></tr>'
            )
        comparison_html = (
            "<h2>基线比对</h2>"
            f"<p>通过率 {report.comparison.pass_rate_before * 100:.0f}% → "
            f"{report.comparison.pass_rate_after * 100:.0f}%"
            f"（{report.comparison.pass_rate_delta * 100:+.0f} 个百分点），"
            f"基线 {report.comparison.baseline_runs} 次运行</p>"
            + "".join(items)
            + "<h2>成本</h2><table><tr><th>指标</th><th>基线</th><th>现在</th><th>变化</th></tr>"
            + "".join(cost_rows)
            + "</table>"
        )

    headline = _headline(report)
    meta = (
        f"{len(report.runs)} 次运行 · {report.passed_runs} 次通过（{report.pass_rate * 100:.0f}%）"
        + " · 断言：" + escape(", ".join(report.asserts) or "（无）")
        + f" · 生成于 {escape(report.generated_at)}"
    )
    body = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{escape(headline)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f"<h1>{escape(headline)}</h1>\n"
        f'<p class="meta">{meta}</p>\n'
        + comparison_html
        + f"<h2>运行</h2>\n<table>\n  <tr>{header}</tr>\n" + "\n".join(rows) + "\n</table>\n"
        + "<h2>失败详情</h2>\n"
        + ("<ul>\n" + "\n".join(failures_html) + "\n</ul>\n" if failures_html else "<p>无</p>\n")
        + "\n</body>\n</html>\n"
    )
    return body


def _headline(report: Report) -> str:
    """一句话结论放在最上面：截图的人要的是这句，不是工具名。"""
    total = len(report.runs)
    if total == 0:
        return "没有找到任何 cassette"
    failed = total - report.passed_runs
    if failed == 0:
        return "%d 次运行，全部通过" % total
    exprs = []
    for _run, failure in report.failures:
        if failure.expr not in exprs:
            exprs.append(failure.expr)
    return "%d 次运行里 %d 次没通过 %s" % (total, failed, "、".join(exprs) or "断言")
