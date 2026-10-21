"""不稳定断言识别（v0.4 第一件）——只做判定核心。

看板上的"退步"可能只是噪声：某条断言本身时红时绿，一次失败说明不了什么。
这里拿多次运行的通过/失败样本判定每条断言稳不稳。

置信区间一律复用 stat.wilson_interval，不另写一份实现。
本模块只做判定，不碰 CLI / 表格 / regress 集成。
"""

from __future__ import annotations

from dataclasses import dataclass

from .stat import wilson_interval

MIN_RUNS = 5
BOUND = 0.99

STABLE_PASS = "STABLE_PASS"
STABLE_FAIL = "STABLE_FAIL"
FLAKY = "FLAKY"
UNRELIABLE = "UNRELIABLE"

VERDICTS = (STABLE_PASS, STABLE_FAIL, FLAKY, UNRELIABLE)
NOISY_VERDICTS = (FLAKY,)  # 只有 FLAKY 会把噪声当信号


class FlakyError(ValueError):
    """样本本身不成立（次数 <= 0、通过数超过次数等）。"""


@dataclass
class Verdict:
    value: str
    passed: int
    runs: int
    low: float
    high: float
    bound: float = BOUND
    min_runs: int = MIN_RUNS
    edge: bool = False  # True 表示"样本内全同侧但没达到 bound"

    @property
    def pass_rate(self) -> float:
        return self.passed / self.runs if self.runs else 0.0

    @property
    def is_noisy(self) -> bool:
        """这条断言能不能用来判断退步：FLAKY 就是噪声源。"""
        return self.value in NOISY_VERDICTS

    @property
    def note(self) -> str:
        ci = f"95% 置信区间 {self.low:.2f}–{self.high:.2f}"
        if self.value == UNRELIABLE:
            need = max(0, self.min_runs - self.runs)
            return (
                f"样本不足：只有 {self.runs} 次运行（要求 ≥ {self.min_runs}），"
                f"{ci} 没有判定力，再跑 {need} 次才谈得上稳定与否"
            )
        if self.value == FLAKY:
            return (
                f"{self.passed}/{self.runs} 时过时不过，{ci}："
                "用它判断退步会把噪声当信号"
            )
        if self.edge:
            word = "全过" if self.value == STABLE_PASS else "全败"
            side = "下界" if self.value == STABLE_PASS else "上界"
            need = runs_needed(self.bound)
            return (
                f"{self.runs}/{self.runs} {word}，但 {ci} 的{side}没到 {self.bound}："
                f"只说明这批样本一致，不是已验证的 {self.bound:.0%} 稳定；"
                f"要那种结论需要 n ≥ {need}"
            )
        if self.value == STABLE_PASS:
            return f"{self.passed}/{self.runs} 通过，{ci} 下界 {self.low:.2f} ≥ {self.bound}：稳定通过"
        return f"{self.passed}/{self.runs} 通过，{ci} 上界 {self.high:.2f} ≤ {1 - self.bound:.2f}：稳定失败"

    def to_dict(self) -> dict:
        return {
            "verdict": self.value,
            "passed": self.passed,
            "runs": self.runs,
            "pass_rate": round(self.pass_rate, 4),
            "low": round(self.low, 4),
            "high": round(self.high, 4),
            "bound": self.bound,
            "min_runs": self.min_runs,
            "edge": self.edge,
            "noisy": self.is_noisy,
            "note": self.note,
        }


def runs_needed(bound: float = BOUND) -> int:
    """全过时需要多少次运行，区间下界才够得着 bound（0.99 → 381）。"""
    n = 1
    while wilson_interval(n, n)[0] < bound:
        n += 1
    return n


def classify(
    passed: int,
    runs: int,
    min_runs: int = MIN_RUNS,
    bound: float = BOUND,
    edge: bool = True,
) -> Verdict:
    """把 (通过数, 运行数) 判成 STABLE_PASS / STABLE_FAIL / FLAKY / UNRELIABLE。

    edge=True（默认）时，样本内全过/全败也算稳定，但 note 会写明区间没到 bound；
    edge=False 是严格字面版：只有区间边界真的够到 bound 才给 STABLE_*，其余 FLAKY。
    """
    if runs <= 0:
        raise FlakyError("运行数必须大于 0")
    if passed < 0 or passed > runs:
        raise FlakyError(f"通过数 {passed} 不可能是 {runs} 次运行的结果")
    if not 0.0 < bound < 1.0:
        raise FlakyError(f"bound 必须在 (0, 1) 之间，实际 {bound!r}")

    low, high = wilson_interval(passed, runs)
    if runs < min_runs:
        return Verdict(UNRELIABLE, passed, runs, low, high, bound, min_runs)

    if low >= bound:
        return Verdict(STABLE_PASS, passed, runs, low, high, bound, min_runs)
    if high <= 1 - bound:
        return Verdict(STABLE_FAIL, passed, runs, low, high, bound, min_runs)
    if edge and passed == runs:
        return Verdict(STABLE_PASS, passed, runs, low, high, bound, min_runs, edge=True)
    if edge and passed == 0:
        return Verdict(STABLE_FAIL, passed, runs, low, high, bound, min_runs, edge=True)
    return Verdict(FLAKY, passed, runs, low, high, bound, min_runs)
