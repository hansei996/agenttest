# 在 pytest 里用 agenttest

不用学第二套 DSL：cassette 是一个 fixture，断言就是 `assert_*` 三个函数，
判定语义和 `agenttest replay --assert` 完全同一套（直接调用 `agenttest.assertions`）。

## 1. 装上（一次）

插件通过标准 `pytest11` 入口点注册，随包一起装：

```bash
python -m pip install -e .     # 或者 pip install agenttest
```

`pyproject.toml` 里对应这两行（已经在本仓库里）：

```toml
[project.entry-points.pytest11]
agenttest = "agenttest.pytest_plugin"
```

pytest 只是开发依赖，不在 `dependencies` 里；没装 pytest 时 `import agenttest`
照常工作，只有 import 这个插件模块才会报错并提示 `pip install pytest`。

## 2. 写测试

```python
from agenttest.pytest_plugin import assert_before, assert_never, assert_tool


def test_agent_reads_logs_first(cassette):
    assert_before(cassette, "quote_error")                  # 先引用报错，再改代码
    assert_tool(cassette, "read_file", path="src/auth.py")  # 读过出事的那个文件
    assert_never(cassette, "delete_file")                   # 没动不该动的工具
```

`cassette` 从哪来，二选一（命令行优先）：

```bash
python -m pytest --agenttest-cassette=examples/good
AGENTTEST_CASSETTE=examples/bad python -m pytest
```

目录（含 `cassette.jsonl`）与 `.jsonl` 文件两种写法都认；相对路径按 pytest
rootdir 解析，所以从仓库任意子目录跑都指向同一份 cassette。
没指定、或 cassette 损坏/找不到时，fixture 直接失败并说清楚缺什么，不走 traceback。

## 3. 失败长什么样

失败信息不重新生成，就是 `agenttest replay` 那一行（`assertions` 模块的原话），
所以"第几个事件违反了哪条契约"在 CLI 和 pytest 里读到的是同一句：

```text
FAIL before:quote_error — 期望在第一次 edit 之前出现引用报错，实际第 4 个事件就是 edit_file(src/auth.py)，全程没有引用过报错 quote_error（没读日志就直接改代码）
  cassette: examples/bad/cassette.jsonl
```

第一行与 `agenttest replay examples/bad --assert before:quote_error` 的输出逐字相同，
第二行是插件补的"这份 cassette 是哪个文件"。

## 4. 三个函数各对应哪条断言

| pytest 里写 | 等价 CLI 断言 |
|---|---|
| `assert_before(cassette, "quote_error")` | `--assert before:quote_error` |
| `assert_tool(cassette, "read_file", path="src/auth.py")` | `--assert tool:read_file(path=src/auth.py)` |
| `assert_never(cassette, "delete_file")` | `--assert never:tool=delete_file` |

`assert_tool` 的参数值按字符串比较（和断言语言一致），所以带逗号的值会被 DSL
的 `key=value` 解析切开——这种参数用 CLI 的 `--assert` 更稳，插件不另造规则。

## 5. 一个进程一份 cassette

就是 `--agenttest-cassette` / 环境变量那一份。要覆盖 good 和 bad 两种行为，
用参数化加外层 pytest 子进程切换：

```python
import subprocess
import sys

import pytest


@pytest.mark.parametrize("target", ["examples/good", "examples/bad"])
def test_cassette_behaviour(target, tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--agenttest-cassette=" + target, "-q"],
        cwd=tmp_path,
    )
    assert proc.returncode == 0
```

本仓库的 `tests/test_pytest_plugin.py` 就是这么测插件自己的：
good 必须通过、bad 必须在第 4 个事件上失败。
