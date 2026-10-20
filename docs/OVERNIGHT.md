# 夜间工作简报（写给你醒来第一眼看的）

一句话：**agenttest 从「只有设计文档」推进到了 v0.2.0（已发布），并在过程中抓出并修掉三个 CI 全绿也发现不了的真实缺陷。**

仓库：https://github.com/hansei996/agenttest · tag `v0.2.0`

---

## 1. 现在能用什么

```bash
pip install -e .                      # 装完直接有 agenttest 命令
agenttest replay run/ --assert before:quote_error      # 断言行为契约
agenttest diff run/a run/b                             # 两次运行的行为差异
agenttest record --repeat 5 runs/ -- <agent 命令>       # 采样
agenttest stat runs/ --assert "success>=0.8"           # 统计判定（按置信区间）
agenttest import logs/openai.jsonl runs/               # 把已有日志变成 cassette
```

pytest 里也能用：`cassette` fixture + `assert_before` / `assert_tool` / `assert_never`。

## 2. 今晚抓到的三个缺陷（都是 CI 绿着、但用户会踩的）

| # | 缺陷 | 谁会发现 | 修法 |
|---|---|---|---|
| 1 | **统计断言把「没证据」判成「证明了」**：n=3 全成功时 `success>=0.99` 判 PASS | 只有拿小样本去试才会发现 | 按 95% 置信区间判定；默认 FAIL，`--point-estimate` 才放行 |
| 2 | **校验器输出 cp936 乱码**：Linux CI 永远是 UTF-8，Windows 上子进程捕获即乱码 | 只有 Windows 上跑全量测试才会发现 | 强制 UTF-8 输出；测试主动摘除 `PYTHONIOENCODING` |
| 3 | **带 BOM 的合法文件被判非法**：一个 BOM 让 4 条校验规则同时红 | 只有用记事本/PowerShell 存过文件才会发现 | 读取容忍 `utf-8-sig`，写出禁止 BOM；UTF-16/二进制/坏 JSON 各自给人话 |

第 3 条顺带把写盘从 `write_text` 换成字节写入，Windows 上不再产生 CRLF——cassette 字节现在跨平台一致。

## 3. 我拒收/退回过的交付

- 统计断言第一次实现时"点估计达标就 PASS"→ 退回重做（就是上面的缺陷 1）
- pytest 插件第一次我测错（测试文件放仓外，rootpath 解析不到）→ 是**我的**测试写错，不是它的实现错，重测通过
- `IMPLEMENTATION-NOTES.md` 被多个 agent 并发改写，一度出现重复小节 → 我核了 HEAD，标题只出现一次，未丢内容

## 4. 状态

```
CI：153 passed（v0.2.0 前一提交）；release 提交的 CI 当时在排队
本地：Windows 沙箱下 36 个 error 全是 pytest tmp_path（mkdtemp 0o700 被沙箱拒），非代码问题
红线执行：0 个新第三方 PR、0 次 force push、0 个仓库被删、密钥扫描 clean
```

## 5. 期间仍在进行

- **v0.3 第一步**：CLI agent 录制适配器（`record-subprocess`）。硬约束是**不许伪造事件**——观测不到 `tool.call` 就写进 `meta.unobserved`，不许编。

## 6. 醒来后建议按这个顺序看

1. `docs/ROADMAP.md` —— 每个版本的验收数字，看 v0.3 之后的方向对不对
2. `docs/CASE-STUDY.md` —— 怎么用它给一个技能写回归（含一个反直觉发现：**坏行为的 token 更少**，成本下降可能是偷工减料的证据）
3. `docs/CASSETTE-SPEC.md` —— 私有格式已经变成别人可实现的规范，且有第三方独立实现 `tools/reference_reader.py` 作证

## 7. 两个我拿不准、需要你拍板的

1. **要不要发发布公告**：v0.2.0 是个真实可用的里程碑，但我按红线没有对外发任何东西（HN/Reddit/掘金都没动）。文案可以沿用 `read-the-logs-first` 那套。
2. **v0.3 之后是不是该做适配器矩阵**（Claude Code / Codex / Cursor 各一套录制），还是先把「统计断言」做成能跨多次运行的回归看板。前者铺得宽，后者更有深度。
