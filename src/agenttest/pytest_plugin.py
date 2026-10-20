"""pytest 插件：把 cassette 和断言直接搬进 pytest，不用再学一套 DSL。

最小用法::

    from agenttest.pytest_plugin import assert_before, assert_never, assert_tool


    def test_agent_reads_logs_first(cassette):
        assert_before(cassette, "quote_error")
        assert_tool(cassette, "read_file", path="src/auth.py")
        assert_never(cassette, "delete_file")

`cassette` fixture 的取值顺序：`--agenttest-cassette=<path>` 优先，其次环境变量
`AGENTTEST_CASSETTE`；目录（含 `cassette.jsonl`）与 `.jsonl` 文件两种写法都认，
相对路径按 pytest rootdir 解析。

判定语义一律复用 :mod:`agenttest.assertions`（这里不另造一套），失败信息与
`agenttest replay` 的输出逐字一致，包含"第几个事件违反了哪条契约"。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # 运行时零第三方依赖：只有真的在 pytest 里用到插件时才需要 pytest
    import pytest
except ImportError as exc:  # pragma: no cover - 只在没装 pytest 的环境里走到
    raise ImportError(
        "agenttest 的 pytest 插件需要 pytest，但当前环境里 import pytest 失败。"
        "agenttest 运行时本身不依赖 pytest；要跑测试请先装：pip install pytest"
    ) from exc

from . import assertions as asrt
from .cassette import CassetteError, cassette_path, read_cassette

ENV_VAR = "AGENTTEST_CASSETTE"
OPTION = "--agenttest-cassette"

__all__ = [
    "AgentTestAssertionError",
    "Cassette",
    "assert_before",
    "assert_never",
    "assert_tool",
    "cassette",
    "load_cassette",
    "pytest_addoption",
]


class AgentTestAssertionError(AssertionError):
    """断言失败：消息是 assertions 模块的原话（与 CLI 失败行一致），另附 cassette 路径。"""

    def __init__(self, result: asrt.AssertionResult, path: Path | None = None) -> None:
        self.expr = result.expr
        self.result = result
        self.cassette_path = path
        message = result.message
        if path is not None:
            message = message + "\n  cassette: " + str(path)
        super().__init__(message)


@dataclass(frozen=True)
class Cassette:
    """一个已经过哈希链校验的事件流，外加它来自哪个文件。"""

    path: Path
    events: list[dict]

    def __len__(self) -> int:
        return len(self.events)


def load_cassette(target: str | Path) -> Cassette:
    """读 cassette（目录或 .jsonl 文件）；损坏/缺失时抛 CassetteError。"""
    path = Path(cassette_path(target))
    events = read_cassette(path)
    return Cassette(path=path, events=events)


def _check(cassette: Cassette, expr: str) -> asrt.AssertionResult:
    result = asrt.evaluate(expr, cassette.events)
    if not result.ok:
        raise AgentTestAssertionError(result, cassette.path)
    return result


def assert_before(cassette: Cassette, token: str) -> asrt.AssertionResult:
    """第一次修改文件之前，必须在模型输出里引用过报错关键字 `token`。"""
    return _check(cassette, "before:" + str(token))


def assert_tool(cassette: Cassette, name: str, **args: object) -> asrt.AssertionResult:
    """必须调用过工具 `name`，且这些参数取值的字符串形式都匹配。"""
    inner = ",".join(str(key) + "=" + str(value) for key, value in args.items())
    return _check(cassette, "tool:" + str(name) + ("(" + inner + ")" if inner else ""))


def assert_never(cassette: Cassette, tool: str) -> asrt.AssertionResult:
    """整个运行里一次都不许调用工具 `tool`。"""
    return _check(cassette, "never:tool=" + str(tool))


def pytest_addoption(parser) -> None:
    group = parser.getgroup("agenttest")
    group.addoption(
        OPTION,
        dest="agenttest_cassette",
        default=None,
        metavar="PATH",
        help="给 cassette fixture 用的 cassette 路径（目录或 cassette.jsonl），也可用环境变量 "
        + ENV_VAR,
    )


def _cassette_target(config) -> Path:
    raw = config.getoption(OPTION, default=None) or os.environ.get(ENV_VAR)
    if not raw:
        pytest.fail(
            "没有指定 cassette：用 "
            + OPTION
            + "=<path> 或环境变量 "
            + ENV_VAR
            + "=<path> 指定一个（目录或 cassette.jsonl 都行），例如 "
            + "python -m pytest "
            + OPTION
            + "=examples/good",
            pytrace=False,
        )
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = Path(str(config.rootpath)) / path
    return path


@pytest.fixture
def cassette(request) -> Cassette:
    """当前测试要用的 cassette；路径来自 --agenttest-cassette 或 AGENTTEST_CASSETTE。"""
    target = _cassette_target(request.config)
    try:
        return load_cassette(target)
    except CassetteError as exc:
        pytest.fail("cassette 加载失败：" + str(exc), pytrace=False)
