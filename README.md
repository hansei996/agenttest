# agenttest

> **让 agent 的行为可以被断言。**
> 录一次运行 → 重放是确定的 → 行为差异结构化 → 概率结论不撒谎。

```bash
pip install -e . && agenttest demo        # 10 秒自证：不联网、不需要 API key
```

```text
agenttest demo — 让 agent 的行为可以被断言

  PASS  replay examples/good   守规矩：先引用报错再改代码
  FAIL  replay examples/bad    偷懒：第 4 个事件就 edit_file，全程没引用报错
  行为差异   新增 调用 edit_file(src/auth.py) · 缺失 引用 quote_error
  回归报告   /tmp/agenttest-demo-xxxx/index.html（单文件、零依赖、离线可开）

  同一个 agent，一次守规矩一次偷懒 —— 工具抓得出区别。
```

## 60 秒接入

```bash
agenttest init                                                    # 生成骨架（只新建，不覆盖）
agenttest record-subprocess runs/latest -- python -m your_agent "你的任务"
AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py
```

你的 agent 已经用 `agenttest.agent.Session` 说话就用 `agenttest record`；手上已有 OpenAI / Anthropic 日志就用 `agenttest import`。

## 遇到这些症状时

| 症状 | 看哪一页 |
|---|---|
| 升级模型 / 改了 prompt 之后感觉行为变了 | [docs/errors/behaviour-changed-after-upgrade.md](./docs/errors/behaviour-changed-after-upgrade.md) |
| agent 测试时过时不过、本地过 CI 不过 | [docs/errors/flaky-agent-tests.md](./docs/errors/flaky-agent-tests.md) |
| Node 的栈指向 `dist/` 或第一帧看不懂 | [docs/errors/node-stack-trace-wrong-frame.md](./docs/errors/node-stack-trace-wrong-frame.md) |
| 只想从别的语言 / 别的进程产出 cassette | [docs/EMIT.md](./docs/EMIT.md) |
| 想给一份 cassette 做一次人工复盘 | `python tools/cassette_view.py runs/latest` |

## 命令一览

| 命令 | 干什么 | 什么时候用 |
|---|---|---|
| `demo` | 一条命令自证，10 秒 | 第一次听说这个工具 |
| `init` | 生成最小回归骨架（不覆盖已有文件） | 想接入自己的仓库 |
| `record` / `record-subprocess` / `import` | 录真实运行 | 有 agent 想被断言 |
| `replay` | 从 cassette 确定性地重放 + 断言 | 每次改代码之后 |
| `diff` | 两次运行的行为差异 | 换模型、改 prompt 前后 |
| `regress` | 多次运行的回归看板（终端 + 单文件 HTML） | 攒了一批运行之后 |
| `regress --flaky-report` | 已知不稳定断言分栏，不冒充退步 | 有噪声但不想关掉看板 |
| `regress --html-views` | 看板里每个 run 下钻到事件浏览页 | 想人工复盘某一次 |
| `flaky` | 量化「时过时不过」到什么程度 | 有人说「它就是不稳定」时 |
| `plan` | 想主张失败率 ≤X%，最少要跑多少次 | 下结论之前 |
| `stat` | 多次运行的统计断言（Wilson 区间） | 关心成功率 / 成本 |
| `export --format junit\|sarif` | 结果进任何 CI 看板 | 要接 CI |

## 为什么需要它

agent 有四类问题，普通单测全都测不到：

| 问题 | 普通单测 | agenttest |
|---|---|---|
| 它到底调用了什么工具、按什么顺序 | ✗ | ✅ cassette 记录全部事件 |
| 它是不是先读日志再改代码（行为契约） | ✗ | ✅ 行为断言 `before:quote_error` |
| 换了模型 / 改了提示词后，哪些行为变了 | ✗ | ✅ `diff` 两份运行 |
| 跑 20 次成功率多少、成本会不会翻倍 | ✗ | ✅ 统计断言 + 置信区间 |

## 设计原则

1. **不绑定 agent 框架**：cassette 是事件流，任何 agent 只要吐得出事件就能被测。
2. **replay 必须确定**：模型输出一律来自 cassette，重放时禁止真实网络调用。
3. **断言只断言可观测行为**，不猜「它想干什么」。
4. **不替数据说它没资格说的话**：样本不够就说样本不够，不把 5 次全过说成「稳定」。

## 文档

- 设计：[docs/DESIGN.md](./docs/DESIGN.md) · 路线：[docs/ROADMAP.md](./docs/ROADMAP.md) · 变更：[docs/CHANGELOG.md](./docs/CHANGELOG.md)
- 格式规范：[docs/CASSETTE-SPEC.md](./docs/CASSETTE-SPEC.md)（含四种已知实现与验证方式）
- 生产端 SDK：[docs/EMIT.md](./docs/EMIT.md) · pytest 插件：[docs/PYTEST.md](./docs/PYTEST.md) · 导入器：[docs/IMPORTERS.md](./docs/IMPORTERS.md)

## License

MIT