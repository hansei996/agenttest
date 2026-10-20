# v0.2.0 发布公告（各渠道可直接粘贴的文案）

> 状态：仓库已发 Release（https://github.com/hansei996/agenttest/releases/tag/v0.2.0）。
> HN / Reddit / X / 掘金 需要账号登录态，本机没有——以下文案由你手工贴。

---

## 1. Show HN（标题 ≤80 字符）

```
Show HN: Test what your AI agent did, not just what it said
```

正文：

```
I kept hitting the same wall: I give an agent a task, it does something,
and afterwards I have no way to prove what it actually did.

Unit tests don't apply. The failure mode isn't a wrong return value, it's
"edited the file before reading the log", "skipped the test run", "called
delete_file when it should have asked".

agenttest records a run as an event stream (model calls, tool calls, file
writes, exit code), replays it deterministically, and lets you assert on
behaviour:

    agenttest replay runs/fix-auth --assert before:quote_error
    agenttest replay runs/fix-auth --assert never:tool=delete_file
    agenttest diff runs/before runs/after

Three things I found while building it that might be useful to others:

1. Cheap is suspicious. The "bad" run that skipped reading the log used
   21% FEWER tokens. Cost going down can be the evidence that the agent
   cut a corner.
2. Statistical assertions need confidence intervals or they lie. n=3 all
   passing does not support "success >= 99%", so the default is to FAIL
   and tell you the sample is too small.
3. Existing logs are enough to start. `agenttest import` converts
   OpenAI/Anthropic message logs into cassettes, so you can assert on
   runs you already have.

Install: pip install agenttest
Docs: https://github.com/hansei996/agenttest

The cassette format is specified (docs/CASSETTE-SPEC.md) and there's a
third-party reference reader that doesn't import the project, so other
tools can implement it.

Happy to answer questions about the event model or the confidence logic.
```

## 2. Reddit r/ClaudeAI / r/LocalLLaMA

标题：

```
I got tired of not being able to prove what my agent actually did, so I made it testable
```

正文（口语，不带小标题）：

```
The thing that kept biting me: after an agent run I could read the transcript,
but I couldn't assert anything. "Did it read the error before editing?" was a
vibe, not a check.

So I made a small tool. It records the run as events, replays it
deterministically, and lets me write assertions like
`--assert before:quote_error` or `--assert never:tool=delete_file`.
Then diff two runs to see what behaviour changed when I swapped models.

Two things surprised me while building it:

- The lazier run was cheaper. Skipping the log read saved 21% of tokens, so
  "cost went down" is not automatically good news.
- My first stat implementation was a liar. With 3 runs all passing it happily
  green-lit "success >= 99%". Now it judges on a 95% interval and fails by
  default when the sample can't support the claim.

It also ingests existing OpenAI/Anthropic logs, so you can test runs you
already have instead of re-running everything.

pip install agenttest — would love feedback on what assertions you'd want.
```

## 3. X / Twitter（≤280 字符）

```
Your agent "did the task" — but can you prove it read the log first?

agenttest replays a run and asserts on behaviour:
--assert before:quote_error
--assert never:tool=delete_file
--assert success>=0.8 (95% CI, not vibes)

Found while building: the lazy run used 21% FEWER tokens.
```

## 4. 中文（掘金 / V2EX 通用，200 字内）

```
agent 说它改好了，可你怎么证明它读过错日志？

agenttest 把一次运行录成事件流（模型调用、工具调用、文件写入、退出码），
确定性重放后可以断言行为：--assert before:quote_error（改代码前必须先引用报错）、
--assert never:tool=delete_file、--assert "success>=0.8"（按 95% 置信区间判，
样本不够会直接失败而不是假装通过）。

两个反直觉的发现：跳过读日志的那次运行 token 少用了 21%，所以成本下降
可能是偷工减料的证据；另外只跑 3 次就说"成功率 99%"是不成立的。

装起来就一条：pip install agenttest
```

---

## 5. 发布前检查清单

- [x] Release 已发（v0.2.0）
- [x] CI 绿（153 passed）
- [x] 第三方独立实现存在（tools/reference_reader.py）——"别人也能实现"这件事有代码作证
- [ ] 手工贴到各渠道（需要你的账号）
- [ ] 贴完把 star 变化记进 docs/OVERNIGHT.md

## 6. 贴之前最好补的一张图

终端里跑这两条，把输出截成一张图，比任何文案都有说服力：

```bash
agenttest replay examples/good --assert before:quote_error     # PASS
agenttest replay examples/bad  --assert before:quote_error     # FAIL + 指出第 4 个事件
```
