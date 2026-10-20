# 怎么用（v0.1）

## 0. 环境

运行时零第三方依赖（纯标准库），只有 `tests/` 需要 pytest。

```bash
pip install -e .          # 装完就有 agenttest 命令，不需要 PYTHONPATH
agenttest --help
agenttest record examples/good -- python examples/fake_agent.py --script good
agenttest replay examples/good --assert before:quote_error
agenttest diff   examples/good examples/bad
pip install pytest && python -m pytest tests -q
```

不想安装也可以：`PYTHONPATH=src python -m agenttest ...`（PowerShell：`$env:PYTHONPATH='src'`）。
`pip install` 会把 `agenttest` 启动器放进当前解释器的 Scripts/bin 目录；
如果那个目录不在 PATH 上，用完整路径调用，或者执行前把它加进 PATH。

## 1. 四个动词

### record

```bash
agenttest record <cassette 目录> -- <agent 命令...>
agenttest record --repeat N <目录> -- <agent 命令...>     # 采样，产 batch.jsonl
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

### stat

```bash
agenttest record --repeat 20 runs/fix-auth -- python -m my_agent "..."
agenttest stat runs/fix-auth/batch.jsonl --assert "success>=0.8" --assert "tokens<=2000"
```

对多次真实运行做统计判定。单次 replay 是确定的，成功率没有意义，所以统计量一律来自
`record --repeat N` 的采样：每次运行的摘要（成功与否、tokens、耗时、工具调用数）写进
`<目录>/batch.jsonl`，每次运行的完整 cassette 留在 `<目录>/runs/run-<i>/cassette.jsonl`（失败可回放复盘）。

支持的统计量与比较符：

| 统计量 | 含义 | 比较符 |
|---|---|---|
| `success` | 成功率（`run.end.exit_code==0` 且 `record --assert` 全过） | `>=` `<=` `>` `<` `==` |
| `tokens` | 每次运行 tokens 的平均值 | 同上 |
| `duration` | 每次运行耗时的平均值（秒） | 同上 |
| `tool_calls` | 工具调用数的平均值（别名 `tools`） | 同上 |
| `runs` | 样本数 | 同上 |

**样本少于 5 次会打印 WARN 并给出成功率的 Wilson 95% 置信区间**，不假装精确。

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
