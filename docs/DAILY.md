# 每日总结

> 格式固定五行，**每天一条，不许跳过**。数字必须来自当天的真实读数，做不到就写「无数据」。
> 这不是日报给别人看的，是防止「一直很忙但没进展」的自检表。

```
## YYYY-MM-DD
产出：<今天真正落地的提交/发布/对外动作，带 sha 或链接>
数字：<star / Traffic uniques / PR 状态 / 其他可测量项，写明读数时间>
卡点：<今天卡在哪，谁该解开它（我 / 队友 / 用户）>
明天三件：<1. 2. 3.，每件必须可判定完成>
队友结论：<今天从某个 teammate 那里得到的一条判断，以及我采纳还是否掉>
```

---

## 2026-10-23

产出：`d09ff81` demo 命令 + action.yml(v1) + [project.urls] + README 首屏 + docs/DISTRIBUTION.md；`cf45847` 修掉假绿（console-script 静默通过）+ 回归测试；`8ddf607` CI 加 Windows job；`dcec227` v0.4.0（flaky 判定改名 + 两个 bug 修复）；发布 v0.3.1、v0.4.0

数字：agenttest / read-the-logs-first / blame-archaeology 三仓 **0 star / 0 fork**；Traffic **0 views / 0 uniques / 无 referrer**（读数 2026-10-21）；PR #1010 OPEN（零评论）、PR #5256 OPEN；测试 212 passed（ubuntu + windows 双 job 绿）

卡点：**曝光 0** —— 所有技术债今天清完，但没有一个人来过。解卡的人是用户（帐号）或清单维护者（合并 PR），不是我。

明天三件：1) 提 ComposioHQ 77k 清单 PR（最大漏项）2) 补 docs/FLAKY.md 3) 自己跑一次 5 分钟陌生人测试并计时

队友结论：`archaeology-transcript` 说「改名不会带来星，它只填掉『当真有人来时必踩的坑』」——采纳，所以改名排在 PR 合并后，先做措辞修正；`skill-ci` 说「Profile README 只影响转化不产生流量」——采纳，从今天的优先级里删掉。

---

## 每日节奏（不许打破）

| 时段 | 干什么 | 为什么 |
|---|---|---|
| 00:30–08:30 | 我亲自实现（不派卡片） | 低谷价，产出窗口 |
| 08:30–09:30 | 写上面那条总结 + 更新数字 | 防止「很忙但没进展」 |
| 白天（峰值） | 讨论 / 评审 / 对外动作（PR、清单、答 issue），不写实现 | 峰值不烧实现，但沟通照常 |
| 每两天一次 | 向三个 teammate 各提一个**真问题**（不是派活） | 今天三份讨论的价值超过了三次实现 |
## 2026-10-24（自循环第 1 轮）

产出：`agenttest export --format junit|sarif`（`src/agenttest/export.py` + CLI + 5 条测试，217 passed）；`read-the-logs-first` 按 awesome-copilot 维护者的意见加了确定性出错帧提取器 `tools/extract_frame.py`（4 条回归测试）+ 各运行时日志位置表，commit `d094337`；在被关闭的 PR #5256 下留了一条带证据的回复，询问是否欢迎重提

数字：三仓仍 0 star；Traffic 0（09:53 读数）；PR #1010 OPEN 零评论；#5256 CLOSED（维护者给了实质理由）

卡点：ComposioHQ（77k 清单）PR 被组织 OAuth 限制挡住，只有用户能授权；除此之外无阻塞

明天三件：（本轮结束时填）

队友结论：`agenttest-mvp` 与 `archaeology-transcript` 都指向「去一条正在发痛的 issue 里给可跑的复现」；`skill-ci` 指向「提最大的那个清单」。三者都需要一个能带人来的动作，而不是更多功能——采纳，本轮做的是「让别人能直接用我们的结果」（JUnit/SARIF 导出）。
## 2026-10-24（自循环第 2 轮）

产出：`agenttest emit` 生产端 SDK（`src/agenttest/emit.py` + `docs/EMIT.md` + 6 条测试，223 passed），commit `96e4690`。别人不用我们的 record/replay，20 行就能写出带哈希链的合规 cassette，且产出的文件能直接过 `tools/validate_cassette.py`、被 `replay`/`diff` 消费。

数字：三仓 0 star；Traffic 0；测试 223 passed（本机）；CI 待跑

卡点：ComposioHQ 组织 OAuth 授权（只有用户能做）；其余无阻塞

为什么这轮做 emit 而不是做功能：格式扩散的唯一引擎是「生产成本足够低」。消费端再强，没人愿意产出 cassette 就没有意义。这一条来自 `archaeology-transcript` 的判断，采纳。
## 2026-10-24（自循环第 3 轮）

产出：两篇长尾报错文档 `docs/errors/behaviour-changed-after-upgrade.md`（升级模型后行为变了）与 `docs/errors/flaky-agent-tests.md`（时过时不过），README 加了「遇到这些症状时」入口表。commit `727b9d3`，223 passed。

为什么做这个：人是用**错误信息**搜索的。这两页覆盖的是「没有栈、只有感觉」的那类问题（行为漂移）与最常见的误判（跑 5 次过 3 次就断言它 flaky）。两页的命令与输出都是本机真跑出来的，不是编的。

数字：三仓 0 star；Traffic 0；223 passed；CI 上一轮 pending→需在下一轮开始时确认

卡点：无（ComposioHQ 授权仍等用户）
## 2026-10-24（自循环第 4 轮）

产出：`read-the-logs-first` v2 —— SKILL.md 改为**自包含**并把「确定性选帧规则 + 各运行时日志位置表」提到第一屏（commit `5347594`）；在 awesome-copilot 的本地 clone 里用**他们自己的** `npm run skill:validate`（441 skills OK）与 `npm run build` 验证通过，分支 `add-read-the-logs-first-skill` @ `b328c9c`，补丁 19,374 字节；提交包与备用 PR 正文落在 agenttest 的 `docs/SUBMISSION-PACK.md`。

关键判断：**不擅自重提**。已在 #5256 下问过是否欢迎重提，没回话就不发——重复提交消耗的是账号信用。

数字：三仓 0 star；Traffic 0；skill 仓库 14 项 skillcheck PASS + 4 条 extractor 测试通过；agenttest 223 passed

卡点：等维护者回话（不是我的阻塞，是对方的节奏）
## 2026-10-24（自循环第 5 轮）

产出：**在第二个仓库里真实验证了 action**——`read-the-logs-first` 新增 `.github/workflows/validate-cassette.yml`，用 `uses: hansei996/agenttest/validate@v1` 消费我们的 action：好 cassette 通过、被篡改的 cassette 必须被拒（并先跑一次好文件证明 action 能加载，避免「加载失败也算失败」的假阳性）。CI run `40052656272` success。

过程中抓到并修掉一个真 bug：`uses: owner/repo/validate@v1` 要求 action.yml 在 `validate/` 子目录里，我们的却在仓库根 → 第一次跑直接 `Can't find 'action.yml'`。修法：新增 `validate/action.yml`（内部 `../tools/validate_cassette.py`），并把浮动的 `v1` tag 移到 `2f106c0`。commit `2f106c0`。

数字：三仓 0 star；Traffic 0；两个 workflow 均绿（skillcheck + cassette contract）

卡点：无

为什么值得：这是我们第一次证明「别人的仓库能用我们的东西」——不是靠自述，是靠别人（我们自己的另一个仓库）的 CI 日志。这条通路是 Marketplace 那条无守门人渠道的前提。
## 2026-10-24（自循环第 6 轮）

产出：`regress --flaky-report` 落地。已知 `MIXED_OBSERVED` 的断言失败被分到**噪声栏**而不是退步栏，终端与 HTML 都分栏，并在「只有噪声失败」时打印一句「未阻止 CI —— 它们被分栏而不是被隐藏」。`INSUFFICIENT_RUNS` **不**算噪声（证据不足不等于可以排除）。新增 4 条测试，227 passed。

实测（基线与当前同一 run id，good→bad）：
```
  新增失败    0 条
  噪声失败    1 条（已知不稳定，不计入退步）
    ~ run-1 / before:quote_error（第 4 个事件）
  注意        本次失败全部来自已知不稳定断言（MIXED_OBSERVED），未阻止 CI —— 它们被分栏而不是被隐藏
```

过程记录：手工打补丁时把 HTML 渲染那段改坏了缩进（parts vs items、4 空格 vs 8 空格），py_compile 当场抓到，修好后 227 全绿。这类错误正是「写完就跑一遍」的价值。

数字：三仓 0 star；Traffic 0；227 passed
## 2026-10-24（自循环第 7 轮）

产出：新增第三篇长尾页 `docs/errors/node-stack-trace-wrong-frame.md`（commit `75167b8`）——讲两件 Node 上最容易搞错的事：V8 栈是**倒序**（第一帧才是抛出点，Python 正好相反），以及栈里出现 `dist/` 时该先开 `--enable-source-maps` 而不是去改编译产物。README 的「遇到这些症状时」表补了这一行。227 passed。

证据来源：页面里的 Node 栈是**本机 node v24.15.0 真跑出来的**（`return raw.timeout` 访问 undefined，10 帧），并用 `tools/extract_frame.py` 跑同一份 stderr，得到 `demo.js:3  (generic, user code)` —— 证明「取第一个用户帧」这条规则在真实 V8 栈上成立。

诚实边界：提取器**不做 source-map 重映射**，页面里写明了这一点以及正确做法（先开 source map，别改 dist）。原本还想写「容器日志」那一页，但本机没有 docker，无法给出真实输出，所以这轮**只写了一页**，不编造命令结果。

数字：三仓 0 star；Traffic 0；227 passed
## 2026-10-24（自循环第 8 轮）

产出：跨语言证明（commit `4aeb672`）——`examples/emit-node/emit.mjs` 用 Node **从零**写出一份 cassette，不 import agenttest、不装任何包，自己实现规范里的三项要求（键按码点升序、逗号冒号后无空格、非 ASCII 原样输出）并算 sha256 链。

实测：
```
$ node examples/emit-node/emit.mjs out/
wrote 6 records to out/cassette.jsonl
$ python tools/validate_cassette.py out/
  结果: PASS（12 条规则全部通过）
```

为什么这条重要：两种语言各自独立实现后算出的哈希能被同一份校验器接受 —— 这就证明 `CASSETTE-SPEC.md` 不再是本仓库的私有约定，而是可被第三方实现的格式。对应测试 `tests/test_emit_node.py`（没装 node 自动跳过）。

数字：三仓 0 star；Traffic 0；228 passed
## 2026-10-24（自循环第 9 轮）

产出：`agenttest plan` 样本量规划（commit `bacf890`，232 passed）。一条命令回答「我想主张失败率 ≤10%，得跑多少次」：
```
  目标下界   需要次数   可排除失败率
  0.90       35         > 10%
  0.99       381        > 1%
```
它不引入新算法——复用 `flaky.runs_needed` 与 `wilson_interval`，存在的理由是让那个数字**可被查**，而不是埋在某条备注里。加了 4 条测试（含「runs_needed 与 plan 必须一致」这条交叉校验）。

数字：三仓 0 star；Traffic 0；232 passed
