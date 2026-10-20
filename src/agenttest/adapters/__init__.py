"""适配器：把"真实 CLI agent 的一次运行"变成 cassette。

v0.3 的第一步。核心取舍只有一条：**只记能观测到的东西，缺的就说缺**。

两种事件来源（互斥，写在 run.start.meta.events_source 里）：

* "agent_stdout"   被测 agent 自己在 stdout 上吐 JSONL 事件（每行一个 JSON 且含
                   type 字段）。这些事件来自 agent 本人，直接采用。
* "os_observation" 只有进程层的观测：argv / cwd / 退出码 / stdout / stderr / 耗时 /
                   工作目录里被改动的文件。此时 **不会** 出现 model.call、tool.call
                   这类事件——它们在进程外面根本看不见。看不见的类型逐条列进
                   run.start.meta.unobserved。

为什么不猜：编造一条 tool.call 会让 cassette 看起来很完整，但它描述的是导入者的
想象，不是被测 agent 的行为。用它做回归测试，等于拿假证据去证明行为没变。

用法：

    from agenttest.adapters import record_subprocess

    outcome = record_subprocess(
        ["python", "my_agent.py", "--task", "fix the bug"],
        "cassettes/run1",
        cwd=".",
        timeout=300,
    )
    print(outcome.events_source, outcome.unobserved)
"""

from __future__ import annotations

from .subprocess_agent import (
    DEFAULT_STREAM_LIMIT,
    AdapterError,
    SubprocessOutcome,
    record_subprocess,
    summarize,
)

__all__ = [
    "DEFAULT_STREAM_LIMIT",
    "AdapterError",
    "SubprocessOutcome",
    "record_subprocess",
    "summarize",
]
