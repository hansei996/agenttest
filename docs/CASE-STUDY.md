# CASE STUDY：给一个「技能」写回归测试

> 被测对象：[read-the-logs-first](https://github.com/hansei996/read-the-logs-first) —— 一个只有 10 条规则、2KB 的 SKILL.md。
> 它的问题和所有技能一样：**规则写了，但没人能证明 agent 真的遵守。**

## 1. 为什么普通单测测不了它

技能的规则是**行为契约**，不是函数：

| 规则 | 普通单测怎么写 | 用 agenttest 怎么写 |
|---|---|---|
| 规则 2：先逐字引用报错 | 测不了（没有返回值） | `--assert before:quote_error` |
| 规则 3：先打开出错的那一帧 | 测不了 | `--assert tool:read_file(path=logs/app.log)` |
| 规则 6：一次只改一处 | 测不了 | 事件序断言（改 → 跑 → 再改） |
| 反面：不许删文件就完事 | 测不了 | `--assert never:tool=delete_file` |

## 2. 做法：把契约写成一条命令

```bash
# 好行为：先读日志、引用报错，再改代码
agenttest replay examples/good --assert before:quote_error

# 坏行为：没过日志就改代码
agenttest replay examples/bad --assert before:quote_error
```

真实输出（本机实测）：

```text
$ agenttest replay examples/good --assert before:quote_error
  cassette  20 条记录，sha256 哈希链完整（cassette.jsonl）
  事件      20 条，与 cassette 完全一致
  PASS      before:quote_error
PASS examples/good  (1 个断言全部通过)          [exit 0]

$ agenttest replay examples/bad --assert before:quote_error
  FAIL before:quote_error — 期望在第一次 edit 之前出现引用报错，
       实际第 4 个事件就是 edit_file(src/auth.py)，
       全程没有引用过报错 quote_error（没读日志就直接改代码）
FAILED examples/bad  (1/1 条断言失败)            [exit 1]
```

**这就是想要的形状**：技能被违反时，失败信息要能直接当 code review 评论读，而不是一句 `AssertionError`。

## 3. 行为差异是可以被机器读出来的

```text
$ agenttest diff examples/good examples/bad
行为差异 (examples/good → examples/bad)
  + 新增  调用 edit_file(src/auth.py)
  - 缺失  调用 read_file(logs/app.log)
  - 缺失  引用 KeyError
  - 缺失  引用 quote_error
  ~ 顺序  开头是 read_file(src/auth.py)，现在开头是 edit_file(src/auth.py)
  成本   tokens 6,800 → 5,380 (-21%) · 耗时 0.016s → 0.015s · 工具调用 4 → 4
```

注意这里有个**真实的陷阱，值得所有用 agent 的人记住**：坏行为的 token 更少（-21%）。
agent 跳过读日志会**更便宜、更快**——所以"成本下降"绝不能单独当成好事来报，这可能正是它偷工减料的证据。

## 4. 接进 CI（技能作者可复制的模板）

```yaml
- name: skill contract
  run: |
    agenttest replay fixtures/real-run --assert before:quote_error
    agenttest replay fixtures/real-run --assert never:tool=delete_file
```

技能仓只要存一份真实运行的 cassette（导入器可以直接吃现有日志：`agenttest import runs/openai.jsonl fixtures/real-run`），就有了回归保护：**改了 SKILL.md 之后，如果 agent 不再遵守规则 2，CI 会红。**

## 5. 这一版做不到的事（诚实边界）

- 本用例的 cassette 来自**脚本化的 agent**（`examples/fake_agent.py`），不是真实模型运行。它能证明"框架能抓住违规"，**不能**证明"真实模型会/不会遵守规则"。
- 真实模型接入需要 v0.3 的适配器（把 CLI agent 或 HTTP agent 的调用录成事件流）。在那之前，正确的用法是：**先用导入器把你已有的真实日志变成 cassette**（`agenttest import`），再对它们写断言——那样断言的结论就是关于真实运行的。
- 统计类结论（"遵守率 80%"）必须用 `record --repeat N` 采样，且注意 agenttest 的默认行为是**按 95% 置信区间判定**，n 太小会直接 FAIL 并告诉你"样本不足"，不允许把点估计当结论。

## 6. 一句话总结

技能的问题从来不是"写得不好"，而是"没人能证明它生效"。agenttest 做的事，是把那条证明变成一条会红的测试。
