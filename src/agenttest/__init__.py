"""agenttest —— 把 agent 的行为当代码来测（v0.3）。

对外动词：record / record-subprocess / replay / diff / stat / regress / import，见 docs/。
运行时零第三方依赖（纯标准库）。
"""

__version__ = "0.3.0"

from . import assertions, cassette, diff, events, guard, regress, stat  # noqa: F401

__all__ = [
    "__version__",
    "assertions",
    "cassette",
    "diff",
    "events",
    "guard",
    "regress",
    "stat",
]
