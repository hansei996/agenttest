"""agenttest —— 把 agent 的行为当代码来测（v0.1）。

对外只有四件事：record / replay / diff / stat，见 docs/DESIGN.md。
运行时零第三方依赖（纯标准库）。
"""

__version__ = "0.1.0"

from . import assertions, cassette, diff, events, guard, stat  # noqa: F401

__all__ = ["__version__", "assertions", "cassette", "diff", "events", "guard", "stat"]
