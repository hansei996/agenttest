# agenttest

> **让 agent 的行为可以被断言。**

`agenttest demo` 一条命令自证（10 秒、不联网、不需要 API key）：

```text
agenttest demo — 让 agent 的行为可以被断言

  PASS  replay examples/good   守规矩：先引用报错再改代码
  FAIL  replay examples/bad    偷懒：第 4 个事件就 edit_file，全程没引用报错
  行为差异   新增 调用 edit_file(src/auth.py) · 缺失 引用 quote_error
  回归报告   /tmp/agenttest-demo-xxxx/index.html（单文件、零依赖、离线可开）

  同一个 agent，一次守规矩一次偷懒 —— 工具抓得出区别。
  下一步：agenttest replay <你的 cassette> --assert before:quote_error
```

```bash
pip install -e . && agenttest demo
```

离线装不上时（build isolation 要联网拉 setuptools，`--no-build-isolation` 在缺 setuptools 的解释器上会报 BackendUnavailable）：
直接 `PYTHONPATH=src python -m agenttest demo` 从源码跑。

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
## 遇到这些症状时

| 症状 | 看哪一页 |
|---|---|
| 升级模型 / 改了 prompt 之后感觉行为变了 | [docs/errors/behaviour-changed-after-upgrade.md](./docs/errors/behaviour-changed-after-upgrade.md) |
| agent 测试时过时不过、本地过 CI 不过 | [docs/errors/flaky-agent-tests.md](./docs/errors/flaky-agent-tests.md) |
| 只想从别的语言/进程里产出 cassette | [docs/EMIT.md](./docs/EMIT.md) |
| 想知道报告怎么进 CI 看板 | `agenttest export --format junit` 或 `--format sarif` |

