"""统计断言（docs/DESIGN.md 第 4 节的 stat:）。

单次 replay 是确定的，成功率没有任何意义；所以统计量来自**多次真实运行**：

    agenttest record --repeat 20 runs/fix-auth -- python -m my_agent "..."
    agenttest stat   runs/fix-auth/batch.jsonl --assert "success>=0.8" --assert "tokens<=2000"

样本少于 MIN_SAMPLE 时必须警告：不假装精确。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import assertions as asrt
from . import events as ev

BATCH_NAME = "batch.jsonl"
MIN_SAMPLE = 5
Z_95 = 1.96

METRICS = ("success", "tokens", "duration", "tool_calls", "runs")
METRIC_ALIASES = {"tool_calls": "tool_calls", "tools": "tool_calls", "tool": "tool_calls"}
OPS = (">=", "<=", "==", ">", "<")
OP_WORDS = {">=": "≥", "<=": "≤", "==": "=", ">": ">", "<": "<"}


class StatError(ValueError):
    """batch 文件坏了，或者统计断言写错了。"""


# -- 单次运行的摘要 -----------------------------------------------------
def summarize_run(events: list, assert_exprs: Iterable[str] = (), index: int = 1) -> dict:
    """把一次运行压成一行摘要：成功与否、tokens、耗时、工具调用数。"""
    results = asrt.evaluate_all(list(assert_exprs), events)
    failures = [r.message for r in results if not r.ok]
    exit_code = ev.run_end(events).get("exit_code")
    tokens_in, tokens_out = 0, 0
    for event in events:
        if event.get("type") != "model.result":
            continue
        usage = event.get("usage") or {}
        tokens_in += int(usage.get("in", 0) or 0)
        tokens_out += int(usage.get("out", 0) or 0)
    duration = round(
        float(ev.run_end(events).get("t", 0.0)) - float(ev.run_start(events).get("t", 0.0)), 4
    )
    return {
        "run": index,
        "ok": exit_code == 0 and not failures,
        "exit_code": exit_code,
        "tokens": tokens_in + tokens_out,
        "duration": duration,
        "tool_calls": len(ev.tool_calls(events)),
        "failures": failures,
    }


def write_batch(target: str | Path, summaries: list) -> Path:
    path = batch_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in summaries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def batch_path(target: str | Path) -> Path:
    path = Path(target)
    if path.name.lower().endswith(".jsonl"):
        return path
    return path / BATCH_NAME


def read_batch(target: str | Path) -> list:
    path = batch_path(target)
    if not path.exists():
        raise StatError(f"找不到 batch 文件：{path}（先用 agenttest record --repeat N 采样）")
    summaries = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise StatError(f"{path} 第 {lineno} 行不是合法 JSON：{exc}") from exc
        if "ok" not in item:
            raise StatError(f"{path} 第 {lineno} 行缺少 ok 字段，不像 batch 摘要")
        summaries.append(item)
    if not summaries:
        raise StatError(f"batch 文件是空的：{path}")
    return summaries


# -- 汇总 ---------------------------------------------------------------
@dataclass
class BatchStats:
    runs: int
    successes: int
    tokens: list = field(default_factory=list)
    durations: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)

    @property
    def success(self) -> float:
        return self.successes / self.runs if self.runs else 0.0

    @property
    def mean_tokens(self) -> float:
        return sum(self.tokens) / len(self.tokens) if self.tokens else 0.0

    @property
    def mean_duration(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else 0.0

    @property
    def mean_tool_calls(self) -> float:
        return sum(self.tool_calls) / len(self.tool_calls) if self.tool_calls else 0.0

    def value(self, metric: str) -> float:
        if metric == "success":
            return self.success
        if metric == "tokens":
            return self.mean_tokens
        if metric == "duration":
            return self.mean_duration
        if metric == "tool_calls":
            return self.mean_tool_calls
        if metric == "runs":
            return float(self.runs)
        raise StatError(f"未知统计量 {metric!r}，可用：{', '.join(METRICS)}")


def summarize_batch(summaries: list) -> BatchStats:
    stats = BatchStats(runs=len(summaries), successes=0)
    for item in summaries:
        if item.get("ok"):
            stats.successes += 1
        stats.tokens.append(int(item.get("tokens", 0) or 0))
        stats.durations.append(float(item.get("duration", 0.0) or 0.0))
        stats.tool_calls.append(int(item.get("tool_calls", 0) or 0))
    return stats


# -- 统计断言 -----------------------------------------------------------
@dataclass
class StatAssertion:
    expr: str
    metric: str
    op: str
    threshold: float


def parse_stat_assertion(expr: str) -> StatAssertion:
    text = expr.strip()
    if text.startswith("stat:"):
        text = text[len("stat:"):].strip()
    for op in OPS:
        head, sep, tail = text.partition(op)
        if sep and head.strip():
            metric = head.strip()
            metric = METRIC_ALIASES.get(metric, metric)
            if metric not in METRICS:
                raise StatError(
                    f"未知统计量 {head.strip()!r}（来自 {expr!r}），可用：{', '.join(METRICS)}"
                )
            try:
                threshold = float(tail.strip())
            except ValueError as exc:
                raise StatError(f"{expr!r} 的阈值不是数字：{tail.strip()!r}") from exc
            return StatAssertion(expr=text, metric=metric, op=op, threshold=threshold)
    raise StatError(f"统计断言写法是 统计量 比较符 阈值，例如 success>=0.8，实际是 {expr!r}")


@dataclass
class StatResult:
    expr: str
    ok: bool
    message: str


def _format_value(metric: str, value: float) -> str:
    if metric == "success":
        return f"{value:.2f}"
    if metric == "tokens":
        return f"{value:,.0f}"
    if metric == "duration":
        return f"{value:.3f}s"
    if metric == "tool_calls":
        return f"{value:.1f}"
    return f"{int(value)}"


def evaluate_stat(assertion: StatAssertion, stats: BatchStats) -> StatResult:
    measured = stats.value(assertion.metric)
    verdict = {
        ">=": measured >= assertion.threshold,
        "<=": measured <= assertion.threshold,
        "==": math.isclose(measured, assertion.threshold, rel_tol=1e-9, abs_tol=1e-9),
        ">": measured > assertion.threshold,
        "<": measured < assertion.threshold,
    }[assertion.op]
    word = "PASS" if verdict else "FAIL"
    measured_text = _format_value(assertion.metric, measured)
    threshold_text = _format_value(assertion.metric, assertion.threshold)
    tail = "达到要求" if verdict else (
        "低于阈值" if assertion.op in (">=", ">") else "超过阈值"
    )
    return StatResult(
        expr=assertion.expr,
        ok=verdict,
        message=(
            f"{word} {assertion.expr} — 实测 {measured_text}"
            f"（{OP_WORDS[assertion.op]} {threshold_text}）{'' if verdict else '，' + tail}"
        ),
    )


# -- 置信度 -------------------------------------------------------------
def wilson_interval(successes: int, runs: int, z: float = Z_95) -> tuple:
    """成功率的小样本置信区间（Wilson），比 p±1.96√(p(1-p)/n) 诚实。"""
    if runs <= 0:
        return (0.0, 1.0)
    p = successes / runs
    denominator = 1 + z * z / runs
    centre = p + z * z / (2 * runs)
    margin = z * math.sqrt(p * (1 - p) / runs + z * z / (4 * runs * runs))
    low = max(0.0, (centre - margin) / denominator)
    high = min(1.0, (centre + margin) / denominator)
    return (low, high)


def confidence_note(stats: BatchStats) -> str | None:
    if stats.runs >= MIN_SAMPLE:
        return None
    if stats.runs == 0:
        return "WARN 没有样本，任何统计量都没有意义"
    low, high = wilson_interval(stats.successes, stats.runs)
    return (
        f"WARN 只有 {stats.runs} 次运行（建议至少 {MIN_SAMPLE} 次）："
        f"成功率 {stats.success:.2f} 的 95% 置信区间是 {low:.2f}–{high:.2f}，"
        "别把这个数字当精确值"
    )


# -- 报告 ---------------------------------------------------------------
def format_report(batch_label: str, stats: BatchStats, results: list) -> str:
    low, high = wilson_interval(stats.successes, stats.runs)
    lines = [f"batch {batch_label} — {stats.runs} 次运行"]
    lines.append(
        f"  成功      {stats.success * 100:.0f}%  ({stats.successes}/{stats.runs})"
        f" · 95% 置信区间 {low:.2f}–{high:.2f}"
    )
    if stats.tokens:
        lines.append(
            f"  tokens    {stats.mean_tokens:,.0f} 平均（{min(stats.tokens):,}–{max(stats.tokens):,}）"
        )
        lines.append(f"  耗时      {stats.mean_duration:.3f}s 平均")
        lines.append(f"  工具调用  {stats.mean_tool_calls:.1f} 平均")
    note = confidence_note(stats)
    if note:
        lines.append(note)
    for result in results:
        lines.append("  " + result.message)
    return "\n".join(lines)


def failed_runs(summaries: list) -> list:
    return [item for item in summaries if not item.get("ok")]
