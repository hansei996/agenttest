# 怎么用（v0.1）

## 0. 环境

运行时零第三方依赖（纯标准库），只有 `tests/` 需要 pytest。
仓库里没有根目录的打包文件（v0.1 的写入范围只到 `src/` `tests/` `examples/` `docs/` `.github/`），
所以把 `src/` 放到 `PYTHONPATH` 上即可：

```bash
PYTHONPATH=src python -m agenttest record examples/good -- python examples/fake_agent.py --script good
PYTHONPATH=src python -m agenttest replay examples/good --assert before:quote_error
PYTHONPATH=src python -m agenttest diff   examples/good examples/bad
PYTHONPATH=src python -m pytest tests -q
```

（Windows PowerShell：`$env:PYTHONPATH='src'`）

## 1. 三个动词

### record

```bash
python -m agenttest record <cassette 目录> -- <agent 命令...>
```

跑一次 agent，把它的全部事件写成 `<目录>/cassette.jsonl`。
agent 通过 `agenttest.agent.Session` 说话（见 `examples/fake_agent.py`），
它是唯一的内置适配器：cassette 是事件流，任何 agent 只要吐事件就能被测。

### replay

```bash
python -m agenttest replay <cassette 目录> [--assert EXPR ...]
```

按 cassette 重放：agent 真的跑、工具真的执行、文件真的改，
但**模型输出全部来自 cassette**，并且 replay 期间装了网络守卫，
任何真实出网都会立刻抛错并指出调用栈。

退出码：`0` 全部断言通过；`1` 有断言失败 / 行为漂移 / 产物不一致 / 模型输出耗尽。

### diff

```bash
python -m agenttest diff <旧 cassette> <新 cassette>
```

按行为对比两次运行，固定输出四类：新增 / 缺失 / 顺序变化 / 成本变化。

## 2. cassette 格式

一行一个事件，JSONL：

```json
{"seq":0,"prev":null,"event":{"t":0.0,"type":"run.start",...},"hash":"<sha256>"}
```

`prev` 是上一条记录的 `hash`，`hash` 是 `sha256(canonical({"seq","prev","event"}))`。
任何一条被改动，`replay` / `diff` 读入时就会报"第 N 条记录被篡改"。

事件类型只有 6 种：`run.start` `model.call` `model.result` `tool.call` `tool.result` `run.end`。

## 3. 断言

| 写法 | 含义 |
|---|---|
| `before:quote_error` | 第一次修改类工具调用之前，模型输出里引用过这个报错关键字 |
| `tool:read_file(path=src/auth.py)` | 调用过某个工具与参数 |
| `never:tool=delete_file` | 从未调用某个工具 |
| `touched:src/auth.py` | 最终产物包含该文件 |
| `exit:0` | 退出码 |
| `stat:success>=0.8,n=20` | **v0.1 未实现**，会明确报错（见下） |

失败信息长这样，一眼看出第几个事件违反了契约：

```
FAIL before:quote_error — 期望在第一次 edit 之前出现引用报错，实际第 4 个事件就是 edit_file(src/auth.py)，全程没有引用过报错 quote_error（没读日志就直接改代码）
```

## 4. 示例

`examples/fake_agent.py` 是一个不真调模型的假 agent（用 `--script good|bad` 选行为），
它真的读文件、真的改 `examples/.work/<script>/src/auth.py`、真的检查测试目标：

* `examples/good`：先引用日志里的 `KeyError: 'quote_error'`，读 `src/auth.py`，再改。
* `examples/bad`：不读日志直接改，改完才回头读，再改一次。

两份 cassette 都是 record 出来的，可以随时重放：

```
$ python -m agenttest replay examples/good --assert before:quote_error
PASS examples/good  (1 个断言全部通过)

$ python -m agenttest replay examples/bad --assert before:quote_error
FAIL before:quote_error — ...
FAILED examples/bad  (1/1 条断言失败)
```

## 5. 与 DESIGN.md 的偏离

见 [IMPLEMENTATION-NOTES.md](./IMPLEMENTATION-NOTES.md)。
