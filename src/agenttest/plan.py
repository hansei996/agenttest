"""plan —— 样本量规划：想把「失败率上限」证到某个水平，最少要跑多少次。

这不是新算法：它复用 flaky.wilson_interval 与 flaky.runs_needed。
存在的理由是让那个数字可被查（而不是埋在备注里），并且反过来用：
你说得出目标，它说得出代价。
"""
from __future__ import annotations

from .flaky import runs_needed, wilson_interval

COMMON_BOUNDS = (0.5, 0.8, 0.9, 0.95, 0.99)


class PlanError(ValueError):
    """目标不可达或参数非法。"""


def plan(bound: float) -> dict:
    """全过时区间下界达到 bound，需要多少次运行。"""
    if not 0.0 < bound < 1.0:
        raise PlanError("--bound 必须在 (0, 1) 之间，收到 " + str(bound))
    n = runs_needed(bound)
    low, high = wilson_interval(n, n)
    return {
        "bound": bound,
        "runs": n,
        "fail_rate_ceiling": round(1.0 - bound, 4),
        "interval_low": round(low, 4),
        "interval_high": round(high, 4),
        "note": (
            "跑 %d 次全部通过，才只能排除失败率 > %s；要达到 ≤%s 需 %d 次"
            % (n, _pct(1.0 - bound), _pct(1.0 - bound), n)
        ),
    }


def table() -> list:
    return [plan(b) for b in COMMON_BOUNDS]


def _pct(value: float) -> str:
    return "%.0f%%" % (value * 100)
