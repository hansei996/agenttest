# IMPORTERS：把已有的日志变成 cassette

`agenttest` 的 cassette 靠 record 从真实运行里录。但真实用户手里已经有一堆
模型日志了——先让这些日志能变成 cassette，才算跨过第一道门槛。

导入器做三件事：**读两种常见格式**、**映射成 v0 的 6 类事件**、**把读不懂的东西
写成 warning 而不是丢掉**。它不发明格式：写盘一律走 `agenttest.cassette.write_cassette`
（同样的 JSONL + sha256 哈希链）。

## 快速开始

```python
from agenttest.importers import load

cassette = load("logs/openai.jsonl")        # 自动判断格式
cassette.write("cassettes/run1")           # 写出 cassettes/run1/cassette.jsonl

print(cassette.counts)      # {'run.start': 1, 'model.call': 5, ...}
print(cassette.warnings)    # 读不懂/缺字段的地方，一条一条列出来
```

需要覆盖默认值时：

```python
load("logs/any.jsonl", format="anthropic-messages", exit_code=1)
```

| 参数 | 说明 |
|---|---|
| `source` | 日志文件路径；也可以直接传已解析好的对象列表（测试用） |
| `format` | `"openai-chat"` / `"anthropic-messages"`；省略则自动判断 |
| `exit_code` | 日志里没有退出码时按 `0` 记录并写 warning；这里可覆盖 |

## 支持的输入

两种格式都接受 **JSONL**（一行一条记录）和 **JSON 数组**；顶层是
`{"turns": [...]}` 这样的对象也能读。每条记录是一轮：

```text
{"request": {...}, "response": {...}}
```

### openai-chat（Chat Completions 风格）

- `request`: `model` / `messages` / `tools`（tools 可以是 OpenAI 的
  `{"type":"function","function":{"name":...}}` 结构，也可以是纯字符串数组）
- `response`: 完整 chat.completion 对象（取 `choices[0].message` + `usage`），
  或者直接给一个 message 对象
- 时间戳：`response.created` 或记录上的 `timestamp`

工具回执是 `role: "tool"` 的消息，通常出现在**下一轮**的 `request.messages`
里；导入器按 `tool_call_id` 配对。

### anthropic-messages（Messages 风格）

- `request`: `model` / `messages` / `system` / `tools`
- `response`: `content` block 数组（`text` / `tool_use`）+ `usage`
- 时间戳：记录或 `response` 上的 `timestamp` / `created_at`

`tool_use` block 成为 `tool.call`；下一条 user 消息里的
`tool_result`（按 `tool_use_id` 配对）成为 `tool.result`，其 `is_error`
映射为 `ok: false`。

## 映射表

| 日志里的东西 | 事件 | 说明 |
|---|---|---|
| 一条记录（一轮） | `model.call` | `request.messages` / `request.tools` 规范化后原样保留 |
| `choices[0].message` 或 `content` 里的 text | `model.result` | `text` + `tool_calls` + `usage` |
| `tool_calls[]` / `tool_use` | `tool.call` | `arguments`（JSON 字符串）解析成 dict，`input` 直接用 |
| `role:"tool"` 消息 / `tool_result` block | `tool.result` | `ok` 取 `is_error` 的反面；`bytes` 是回执正文的 UTF-8 字节数 |
| `usage.prompt_tokens` / `completion_tokens` | `usage: {"in","out"}` | Anthropic 用 `input_tokens` / `output_tokens` |
| 文件开头 | `run.start` | `agent: "imported:<格式>"`，`argv: []`，`cwd: "."` |
| 文件结尾 | `run.end` | `exit_code` 默认 0，`files_changed: []` |

## 时间戳：不许伪装成真实时间

- **每一轮都有时间戳** → 用真实值，`t` = 该轮时间戳减去第一轮（秒）。
- **任何一轮缺时间戳** → 全部按事件序号合成：`t = index * 0.1`。
  同时在 `run.start.meta.synthetic_timestamps` 写 `true`，并在
  `meta.warnings` 里写一条明说"不是真实时间"的说明。

两条路都不会把合成时间混进真实时间：要么全真，要么全合成。写出来的 cassette
里可以直接读到这个标记：

```text
{"event":{"type":"run.start", ..., "meta":{"synthetic_timestamps":true,"warnings":[...]}}, ...}
```

## warnings：读不懂就说出来

映射不了的东西不会静默消失。目前会写 warning 的情况：

| 情况 | warning 大意 |
|---|---|
| content block 类型不认识（`image`、`thinking`…） | "里有无法映射的 content block 类型：image" |
| `arguments` 不是合法 JSON | "的 arguments 不是合法 JSON，原样保留"（记进 `__raw_arguments__`） |
| `tool.call` 找不到回执 | "没有对应的 tool_result…只记了 tool.call" |
| 回执找不到对应的调用 | "tool_result id=… 找不到对应的 tool_call，已丢弃" |
| 日志里没有退出码 | "run.end.exit_code 不在日志里，按 0 记录" |
| 日志里没有产物改动 | "run.end.files_changed 记为空…replay 的产物比对会跳过" |
| 格式判断不出来 | "无法从内容判断日志风格，按 openai-chat 处理" |
| 时间戳缺失 | "synthetic timestamps: …t = index * 0.1s，不是真实时间" |

warnings 同时出现在两个地方：`cassette.warnings`（返回值）和写盘后的
`run.start.meta.warnings`（可核验的痕迹）。

## 确定性

同一个输入 load 两次，事件列表逐项相等、写出来的文件逐字节相等——没有时间戳
取自"现在"，也没有字典序抖动（canonical JSON 排序键）。

## 能力边界（说清楚，不假装）

- **导入的 cassette 不能直接 replay。** replay 要重跑 `run.start.argv` 里的
  agent，而日志里没有 agent 可跑，所以 `argv` 记成 `[]`。导入的 cassette 适合
  **看**、**diff**、**跑断言**（`agenttest.assertions.evaluate_all` 直接吃事件流）；
  要 replay，得把 argv 指向你自己的 agent。
- **`files_changed` 永远是空的**：日志不含产物信息，所以 replay 的产物哈希比对
  对导入的 cassette 会跳过。
- **`ok` 有猜测成分**：OpenAI 的日志没有回执状态字段，一律记 `ok: true`；
  Anthropic 有 `is_error` 才如实映射。
- **usage 只认主字段**：`cache_creation_input_tokens` 之类口径不同的字段不进
  `usage.in`，但会写一条 warning 说明。

## 示例

`examples/import/` 下两份日志录的是**同一段对话**：

```bash
PYTHONPATH=src python examples/import/demo.py --out .work/import-demo
```

它会导入两份日志、写盘、校验哈希链、跑断言，最后 diff 两者。因为对话相同，
四类行为差异全为"（无）"——格式不同、行为相同，这就是映射正确性的证据。
