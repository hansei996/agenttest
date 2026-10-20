# agenttest

> **把 agent 的行为当代码来测。**

record 一次真实运行 → replay 到确定状态 → 断言它的行为 → 改了 prompt / 换了模型 / 升级工具后，看哪些行为悄悄变了。

```bash
agenttest record ./runs/fix-auth -- python -m my_agent "修复 src/auth.py 的崩溃"
agenttest replay ./runs/fix-auth --assert touched:src/auth.py --assert before:quote_error
agenttest diff   ./runs/before ./runs/after      # 两份 cassette 的行为差异
```

## 为什么需要它

agent 有三类问题，现有测试全都测不到：

| 问题 | 普通单测 | agenttest |
|---|---|---|
| 它到底调用了什么工具、按什么顺序 | ✗ | ✅ cassette 记录全部事件 |
| 它是不是先读日志再改代码（行为契约） | ✗ | ✅ 行为断言 `before:quote_error` |
| 换了模型 / 改了提示词后，哪些行为变了 | ✗ | ✅ `diff` 两份运行 |
| 跑 20 次成本翻倍吗、成功率多少 | ✗ | ✅ 统计断言 |

## 三个动词

- **record**：跑一次 agent，把所有可观测事件（模型调用、工具调用、文件写入、退出码）落成 `cassette.jsonl`。
- **replay**：从 cassette 重放，模型响应被固定，因此**测试是确定的**。
- **diff**：把两次运行的行为差异结构化输出（新增/删除/顺序变化的工具调用、产物差异）。

## 设计原则

1. **不绑定 agent 框架**。cassette 是事件流，任何 agent 只要吐出事件就能被测。
2. **replay 必须确定**。模型输出一律来自 cassette；真实网络调用在 replay 时被禁止（否则测试无意义）。
3. **断言只断言可观测行为**，不猜测"它想干什么"。

详见 [docs/DESIGN.md](./docs/DESIGN.md)。

## License

MIT
