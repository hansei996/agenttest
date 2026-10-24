# 生产端 SDK（emit）

> 格式扩散只有一个引擎：**生产成本足够低**。消费端（replay / diff / regress）再强，没人愿意产出 cassette 就没有意义。
> 所以这里给出不用我们的 runner 也能写合规 cassette 的一条路——20 行以内。

## 最小用法

```python
from agenttest import emit

run = emit.Run(agent="my-agent", argv=["python", "agent.py"])
run.model_call([{"role": "user", "content": "fix the crash"}], tools=["read_file"])
run.model_result(
    "先看日志",
    tool_calls=[{"name": "read_file", "args": {"path": "logs/app.log"}}],
    usage={"in": 900, "out": 120},
)
run.tool_call("read_file", {"path": "logs/app.log"})
run.tool_result("read_file", ok=True, bytes=66)
run.end(exit_code=0, files={"src/auth.py": None})
run.write("runs/fix-auth")        # 写出 runs/fix-auth/cassette.jsonl，带 sha256 哈希链
```

写完之后，我们的工具立刻能处理它：

```bash
agenttest replay runs/fix-auth --assert before:quote_error
agenttest diff runs/before runs/after
python tools/validate_cassette.py runs/fix-auth
```

## 它保证什么

| 保证 | 说明 |
|---|---|
| 只有一种磁盘格式 | 写出复用 `cassette.write_cassette`，不存在 emit 专用格式 |
| 必填字段自动补齐 | `env_fingerprint`、`model`、`usage`、`tool.result.bytes`、`run.end.files_changed` 都有默认值，不会因为少填一个字段就写出坏文件 |
| 顺序不可乱来 | `end()` 之前不能 `write()`；`end()` 之后不能再追加事件，都会抛 `EmitError` |
| 时间戳单调 | `t` 是相对起点的秒数，自动记录 |

## 它不保证什么

- **不保证你录的是真实运行**：emit 只是一个写入器，它不知道你的 agent 到底做了什么。要「可核验」，请用 `record`（从真实进程观测）或 `import`（从真实日志映射）。
- **不校验语义**：它只保证字段齐全 + 哈希链正确，不保证事件序列对得上（例如 `tool.call` 没有配对的 `tool.result`）。

## 什么时候该用它

- 你的 agent 跑在别的语言/进程里，只想在退出前吐出一份结构化的运行记录
- 你想把已有的 trace（OpenTelemetry、自研日志）映射成 cassette，但不想写一个完整 importer
- 你要在测试里手搓一份最小 cassette（例如构造一个「必须失败」的对照样本）
