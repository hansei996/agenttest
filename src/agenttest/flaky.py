"""不稳定断言识别（v0.4）——判定核心 + 终端表格。

看板上的"退步"可能只是噪声：某条断言本身时红时绿，一次失败说明不了什么。
这里拿多次运行的通过/失败样本，描述**观察到了什么**，而不是下"稳定/不稳定"的结论：

    PASSED_IN_ALL_RUNS   这批运行里全过
    FAILED_IN_ALL_RUNS   这批运行里全败
    MIXED_OBSERVED       时过时不过（噪声源）
    INSUFFICIENT_RUNS    样本不够，不给判定

置信区间一律复用 stat.wilson_interval，不另写一份实现。
旧名（STABLE_PASS / STABLE_FAIL / FLAKY / UNRELIABLE）只作为 alias 存在，
终端与 HTML 输出里不允许出现。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from .stat import wilson_interval

MIN_RUNS = 5
BOUND = 0.99

PASSED_IN_ALL_RUNS = "PASSED_IN_ALL_RUNS"
FAILED_IN_ALL_RUNS = "FAILED_IN_ALL_RUNS"
MIXED_OBSERVED = "MIXED_OBSERVED"
INSUFFICIENT_RUNS = "INSUFFICIENT_RUNS"

VERDICTS = (PASSED_IN_ALL_RUNS, FAILED_IN_ALL_RUNS, MIXED_OBSERVED, INSUFFICIENT_RUNS)
NOISY_VERDICTS = (MIXED_OBSERVED,)  # 只有它会把噪声当信号

# 旧名只是 alias，只进 legacy 字段，不进任何人类可读输出
STABLE_PASS = PASSED_IN_ALL_RUNS
STABLE_FAIL = FAILED_IN_ALL_RUNS
FLAKY = MIXED_OBSERVED
UNRELIABLE = INSUFFICIENT_RUNS

LEGACY_NAMES = {
    PASSED_IN_ALL_RUNS: "STABLE_PASS",
    FAILED_IN_ALL_RUNS: "STABLE_FAIL",
    MIXED_OBSERVED: "FLAKY",
    INSUFFICIENT_RUNS: "UNRELIABLE",
}

NOISE_HINT = "用它判断退步会把噪声当信号"


class FlakyError(ValueError):
    """样本本身不成立（次数 <= 0、通过数超过次数等），或者输入根本不是 cassette。"""


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def runs_needed(bound: float = BOUND) -> int:
    """全过时需要多少次运行，区间下界才够得着 bound（0.99 → 381）。"""
    n = 1
    while wilson_interval(n, n)[0] < bound:
        n += 1
    return n


@dataclass
class Verdict:
    value: str
    passed: int
    runs: int
    low: float
    high: float
    bound: float = BOUND
    min_runs: int = MIN_RUNS
    edge: bool = False  # True 表示"样本内全同侧，但区间边界没达到 bound"

    @property
    def pass_rate(self) -> float:
        return self.passed / self.runs if self.runs else 0.0

    @property
    def fail_rate_upper(self) -> float:
        """由区间下界反推：这批全过只排除掉这么大的失败率。"""
        return 1.0 - self.low

    @property
    def legacy(self) -> str:
        return LEGACY_NAMES[self.value]

    @property
    def is_noisy(self) -> bool:
        return self.value in NOISY_VERDICTS

    @property
    def hint(self) -> str:
        """表格末尾那列的短提示：把"离结论还有多远"写在明面上。"""
        if self.value == INSUFFICIENT_RUNS:
            return "样本不足，再跑 " + str(max(0, self.min_runs - self.runs)) + " 次"
        if self.value == MIXED_OBSERVED:
            return NOISE_HINT
        if self.edge:
            target = self.bound if self.value == PASSED_IN_ALL_RUNS else 1.0 - self.bound
            return f"区间未达 {_pct(target)}，需 n ≥ {runs_needed(self.bound)}"
        return "区间达标"

    @property
    def note(self) -> str:
        ci = f"95% 置信区间 {self.low:.2f}–{self.high:.2f}"
        if self.value == INSUFFICIENT_RUNS:
            need = max(0, self.min_runs - self.runs)
            return (
                f"样本不足：只有 {self.runs} 次运行（要求 ≥ {self.min_runs}），"
                f"{ci} 没有判定力，再跑 {need} 次才谈得上有没有抖动"
            )
        if self.value == MIXED_OBSERVED:
            return f"{self.passed}/{self.runs} 时过时不过，{ci}：{NOISE_HINT}"
        if self.edge:
            if self.value == PASSED_IN_ALL_RUNS:
                head = f"{self.passed}/{self.runs} 全过，但区间下界 {self.low:.2f} < {self.bound:g}"
                tail = f"不是已验证的 {self.bound:.0%} 稳定"
            else:
                target = 1.0 - self.bound
                head = f"{self.passed}/{self.runs} 全败，但区间上界 {self.high:.2f} > {target:g}"
                tail = f"不是已验证的 {target:.0%} 失败率"
            return (
                f"{head}（{ci}）：只说明这批样本一致，{tail}；"
                f"要那种结论需要 n ≥ {runs_needed(self.bound)}"
            )
        if self.value == PASSED_IN_ALL_RUNS:
            return (
                f"{self.passed}/{self.runs} 全过，{ci} 下界 {self.low:.2f} ≥ {self.bound:g}："
                "观察到的一致性够得上这个阈值"
            )
        return (
            f"{self.passed}/{self.runs} 全败，{ci} 上界 {self.high:.2f} ≤ {1.0 - self.bound:g}："
            "观察到的一致性够得上这个阈值"
        )

    def to_dict(self) -> dict:
        return {
            "verdict": self.value,
            "legacy": self.legacy,
            "passed": self.passed,
            "runs": self.runs,
            "pass_rate": round(self.pass_rate, 4),
            "low": round(self.low, 4),
            "high": round(self.high, 4),
            "bound": self.bound,
            "min_runs": self.min_runs,
            "edge": self.edge,
            "noisy": self.is_noisy,
            "fail_rate_upper": round(self.fail_rate_upper, 4),
            "note": self.note,
        }


def classify(
    passed: int,
    runs: int,
    min_runs: int = MIN_RUNS,
    bound: float = BOUND,
    edge: bool = True,
) -> Verdict:
    """把 (通过数, 运行数) 判成上面四个"观察到什么"的分档。

    edge=True（默认）时，样本内全过/全败也算进对应的对称档，但 note 会写明区间没到 bound；
    edge=False 是严格字面版：只有区间边界真的够到 bound 才给前两档，其余 MIXED_OBSERVED。
    """
    if runs <= 0:
        raise FlakyError("运行数必须大于 0")
    if passed < 0 or passed > runs:
        raise FlakyError(f"通过数 {passed} 不可能是 {runs} 次运行的结果")
    if not 0.0 < bound < 1.0:
        raise FlakyError(f"bound 必须在 (0, 1) 之间，实际 {bound!r}")

    low, high = wilson_interval(passed, runs)
    if runs < min_runs:
        return Verdict(INSUFFICIENT_RUNS, passed, runs, low, high, bound, min_runs)
    if low >= bound:
        return Verdict(PASSED_IN_ALL_RUNS, passed, runs, low, high, bound, min_runs)
    if high <= 1 - bound:
        return Verdict(FAILED_IN_ALL_RUNS, passed, runs, low, high, bound, min_runs)
    if edge and passed == runs:
        return Verdict(PASSED_IN_ALL_RUNS, passed, runs, low, high, bound, min_runs, edge=True)
    if edge and passed == 0:
        return Verdict(FAILED_IN_ALL_RUNS, passed, runs, low, high, bound, min_runs, edge=True)
    return Verdict(MIXED_OBSERVED, passed, runs, low, high, bound, min_runs)


# -- 一批 cassette 的汇总 -----------------------------------------------
@dataclass
class FlakyRow:
    expr: str
    verdict: Verdict

    @property
    def value(self) -> str:
        return self.verdict.value

    def to_dict(self) -> dict:
        return {"expr": self.expr, **self.verdict.to_dict()}


@dataclass
class FlakyReport:
    rows: list
    runs: int
    min_runs: int = MIN_RUNS
    generated_at: str = ""

    @property
    def unreliable(self) -> bool:
        """整表是不是都没有判定力（少于 --min-runs）。"""
        return bool(self.rows) and all(row.value == INSUFFICIENT_RUNS for row in self.rows)

    @property
    def noisy(self) -> list:
        return [row for row in self.rows if row.value == MIXED_OBSERVED]

    def to_dict(self) -> dict:
        return {
            "schema_version": "0.1.0",
            "generated_at": self.generated_at,
            "min_runs": self.min_runs,
            "runs": self.runs,
            "unreliable": self.unreliable,
            "asserts": [row.to_dict() for row in self.rows],
        }


def collect(paths, asserts, min_runs: int = MIN_RUNS, bound: float = BOUND) -> FlakyReport:
    """对一个或多个 cassette 目录跑同一批断言，返回每条断言的观察结果。

    发现规则与逐 run 求值都复用 regress（同一套 cassette 布局与断言求值语义）。
    将来 regress 要反向用 flaky 时，请用函数内延迟 import，别造成模块级循环。
    """
    from . import regress as rg

    asserts = list(asserts)
    if not asserts:
        raise FlakyError("至少要一条 --assert：flaky 判定的是断言，不是 cassette 本身")
    rg.check_assertions(asserts)

    cassettes = []
    for path in paths:
        for run_id, cassette in rg.discover_runs(path):
            cassettes.append((f"{path}::{run_id}", cassette))
    if not cassettes:
        raise FlakyError("没有找到任何 cassette")

    marks = {expr: [] for expr in asserts}
    for run_id, cassette in cassettes:
        run = rg.summarize_run(run_id, cassette, asserts)
        if run.error:
            raise FlakyError(f"cassette 读不了（{run_id}）：{run.error}")
        for result in run.assertions:
            marks[result.expr].append(bool(result.ok))

    rows = [
        FlakyRow(expr=expr, verdict=classify(sum(marks[expr]), len(marks[expr]), min_runs, bound))
        for expr in asserts
    ]
    return FlakyReport(
        rows=rows,
        runs=len(cassettes),
        min_runs=min_runs,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# -- 终端表格 -----------------------------------------------------------
def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def footer_line(report: FlakyReport) -> str:
    runs = report.runs
    if runs <= 0:
        return "本表 n=0；没有样本，任何判定都不成立"
    low, _ = wilson_interval(runs, runs)
    return (
        f"本表 n={runs}；{runs} 次全过只排除失败率 > {_pct(1.0 - low)}，"
        f"要到 ≤{_pct(1.0 - BOUND)} 需 {runs_needed(BOUND)} 次"
    )


def render_table(report: FlakyReport) -> str:
    header = ["断言", "运行数", "通过", "通过率", "95% CI", "判定", "备注"]
    rows = [header]
    for row in report.rows:
        verdict = row.verdict
        rows.append(
            [
                row.expr,
                str(verdict.runs),
                str(verdict.passed),
                _pct(verdict.pass_rate),
                f"{verdict.low:.2f}–{verdict.high:.2f}",
                verdict.value,
                verdict.hint,
            ]
        )
    widths = [max(_display_width(r[i]) for r in rows) for i in range(len(header))]
    lines = [f"flaky — {report.runs} 次运行，{len(report.rows)} 条断言"]
    for index, row in enumerate(rows):
        if index == 1:
            lines.append("  " + "  ".join("-" * width for width in widths))
        lines.append("  " + "  ".join(_pad(c, widths[i]) for i, c in enumerate(row)).rstrip())
    lines.append(footer_line(report))
    if report.unreliable:
        need = max(0, report.min_runs - report.runs)
        lines.append(
            f"{INSUFFICIENT_RUNS} 整表：本表只有 {report.runs} 次运行"
            f"（< --min-runs {report.min_runs}），上面的判定都不成立，"
            f"再跑 {need} 次才谈得上有没有抖动"
        )
    return chr(10).join(lines)


def gate_exit_code(report: FlakyReport, fail_on: str = "never") -> int:
    if fail_on not in ("never", "flaky"):
        raise FlakyError(f"--fail-on 只支持 never/flaky，收到 {fail_on!r}")
    if fail_on == "never":
        return 0
    return 1 if report.noisy else 0
