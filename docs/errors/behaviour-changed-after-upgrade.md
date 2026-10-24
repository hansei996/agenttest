# 「升级了模型/prompt 之后，agent 的行为变了」

搜到这一页的人，通常手上没有报错，只有一句**感觉**：好像不如以前了。
这正是 agent 最难排查的一类问题——没有栈、没有断言、没有红绿。

## 结论先说

先不要改代码。先回答一个问题：**是什么行为变了？** 如果答不出来，说明你的 agent 从来没有被断言过，
那就先把它的一次运行录下来，再谈变化。

```bash
# 1) 录下「以前好」的那次运行
agenttest record runs/before -- python -m my_agent "修复 src/auth.py 的崩溃"

# 2) 升级模型 / 改 prompt

# 3) 录下「现在」的那次运行
agenttest record runs/after -- python -m my_agent "修复 src/auth.py 的崩溃"

# 4) 让差异自己说话
agenttest diff runs/before runs/after
```

真实输出（本仓库 examples）：

```text
行为差异 (examples/good → examples/bad)
  + 新增  调用 edit_file(src/auth.py)
  - 缺失  调用 read_file(logs/app.log)
  - 缺失  引用 KeyError
  - 缺失  引用 quote_error
  ~ 顺序  开头是 read_file(src/auth.py)，现在开头是 edit_file(src/auth.py)
  成本   tokens 6,800 → 5,380 (-21%) · 耗时 0.016s → 0.015s · 工具调用 4 → 4
```

## 这张表里最容易读错的一行

**成本那一行显示 -21%：坏的那次更便宜。**

跳过读日志、少跑一次测试、不走查证流程，都会让 token 和耗时下降。所以**成本下降不是好消息，
除非通过率同时在涨**。把这两行并排看，是读这类报告的唯一正确姿势。

## 那到底「哪里变了」

三种情况要分开处理：

| 差异长什么样 | 说明 | 怎么办 |
|---|---|---|
| 少了某个 `tool.call` | agent 跳过了某个步骤 | 这是行为退化，加断言锁住它 |
| `~ 顺序` 变了 | 步骤一样但次序变了 | 常常是 prompt 里示例顺序影响，属可接受但要记录 |
| 成本变了而步骤没变 | 只是 token 化差异 | 不是退化，别改代码 |

## 把它变成不会复发的东西

```bash
# 把这次「好」的结果存成基线
agenttest regress runs/before --assert before:quote_error --out baseline

# 以后每次改 prompt / 换模型都跟基线比
agenttest regress runs/after --assert before:quote_error --baseline baseline/report.json --out now
```

有新增失败时 `regress` 默认 exit 1，可以直接当 CI 门禁。

## 常见误判

- **「跑两次结果不一样，所以工具没用」** → 那是 agent 本身不确定，先看 [agent 测试不稳定怎么办](./flaky-agent-tests.md)。
- **「我改了 prompt，但 diff 显示没变化」** → 说明这次改动没影响行为，好事，不用继续调。
- **「diff 差异太多看不懂」** → 先只断言一条你最在乎的行为（例如「改代码前必须先读日志」），其余先别看。
