# 错误排查索引

agent 的 bug 多数不是崩溃，而是「感觉不对」：没有栈、没有报错、没有红绿。这三页专治那种情况。

| 你搜到的症状 | 页 | 一句话答案 |
|---|---|---|
| 升级模型 / 改了 prompt 之后感觉行为变了 | [behaviour-changed-after-upgrade](./behaviour-changed-after-upgrade.md) | 先录两份运行做 diff；成本下降不是好消息，除非通过率也在涨 |
| agent 测试时过时不过、本地过 CI 不过 | [flaky-agent-tests](./flaky-agent-tests.md) | 先量化：5 次过 3 次的 95% 区间是 0.23–0.88，「不稳定」这个结论下不了 |
| Node 的栈指向 `dist/`、第一帧看不懂 | [node-stack-trace-wrong-frame](./node-stack-trace-wrong-frame.md) | V8 栈是最内层在前，Python 相反；看到编译产物先开 source map |

## 通用的三步

1. **先取得证据**：跑出 `file:line` 或事件序号，而不是凭印象。
2. **再量化**：跑几次、区间多少；n 小就直说 n 小。
3. **最后才改**：一次只改一处，用同一条命令复现验证。
