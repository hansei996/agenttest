# 今日总结（2026-10-24）

> 今天分两段 goal 跑完 **20 轮**，每轮都有提交。数字全部来自当天真实读数。

## 一句话

**技术债在往下减，曝光债一分没还。251 个测试不能变成 1 个陌生人。**

## 产出（20 轮 / 40 个提交）

| 轮 | 交付 | 复跑方式 |
|---|---|---|
| R1–R12 | `export` JUnit/SARIF、`emit` SDK、两篇长尾页、skill v2、action 跨仓验证、`--flaky-report` 分栏、Node 栈页、跨语言证明、`plan`、HTML 首屏结论、`init`、互操作附录 | `python tools/verify_all.py` |
| R13 | 陌生人测试：发现 `init` 指向了 99% 用户用不了的录制路径，修掉 | 见下方「陌生人 1 秒」 |
| R14 | dogfood 进 CI（两个平台各跑一次噪声分栏） | `python tools/dogfood.py` |
| R15 | 单文件离线查看器（断链当场报、`meta.unobserved` 必显） | `python tools/cassette_view.py examples/good` |
| R16 | README 重排成一屏入口（原 License 夹在正文中间） | 看 `README.md` 前 40 行 |
| R17 | 量化「抖动」→ 不是抖动：查看器 cp936 乱码 bug | 已并入 verify_all 第 8 条 |
| R18 | 同一坑横向排查：`dogfood.py` 也漏了；加 lint 测试兜底 | `pytest tests/test_encoding_guard.py` |
| R19 | `llms.txt` + 错误索引（曝光侧唯一在我权限内的事） | 看 `llms.txt` |
| R20 | 所有主张变成一条命令：`verify_all.py` + 生成的 `docs/VERIFY.md` | `python tools/verify_all.py` |

## 真实数字（2026-10-24 收盘读数）

```
今天的提交        40 个（含 13 个功能/修复，其余文档与日报）
测试              251 passed（本机）；verify_all 8/8
CI                windows 上真的抓到过 cp936 那个 bug（run 40087231408），已修
                  —— 但也暴露另一件事：最近 20 次 run 里 15 次被 cancel-in-progress 取消，
                     等于「push 了但常常没有完成的证据」。已改成只在 PR 上取消，
                     修完连推两次分别 1m55s / 1m6s 全部 success（run 40087645110 / 40087634415）。
star              0 / 0 / 0（agenttest、read-the-logs-first、blame-archaeology）
forks / watchers  0 / 0
Traffic           0 views / 0 uniques（此前读数，今晚未变）
```

## 今天最诚实的三句

1. **「一次绿」不构成证据** —— 我把一条红记成「环境抖动」，跑 10 次才发现它 10/10 全红，是我的环境变量在替我掩盖 bug。
2. **同一个坑踩了三次**（编码）之后才加 lint —— 靠记忆是靠不住的，只能靠规则。
3. **门擦干净不等于有人敲门** —— `llms.txt` / 索引 / README 都是把门擦干净；两周后 Traffic 若仍为 0，说明问题不在这层。

## 仍然只有你能做的两件事

1. **R4 公开发帖**（在真实 issue 里给一份可跑复现）：原文待你过目，你不点头我不发。
2. **ComposioHQ（77,491★ 清单）OAuth 授权**：Settings → Applications → GitHub CLI → Authorize。

---
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
## 2026-10-24（自循环第 10 轮）

产出：HTML 报告首屏改成**一句话结论**（commit 见 git log，235 passed）。原来是 `<h1>agenttest regress</h1>` + 一行含绝对路径的 meta —— 截图的人要的是结论，不是工具名。现在：
```
<h1>2 次运行里 1 次没通过 before:quote_error</h1>
```
同时把根目录绝对路径从 meta 里去掉（`C:/Users/.../tmp.UY0J82fWV6` 这种噪声占了注意力最高的位置），基线比对块提到表格之前。加了 3 条测试：结论必须出现、全过时结论要说全过、绝对路径不许泄漏。

过程：这轮手工改模板踩了两次语法错（多留一个 `return (`、结尾多一个 `)`），都是 `py_compile` 当场抓到的。手工 patch 源码 + 立刻编译，是这轮唯一没翻车的原因。

数字：三仓 0 star；Traffic 0；235 passed
## 2026-10-24（自循环第 11 轮）

产出：`agenttest init`（239 passed）。在任意仓库一条命令生成最小回归骨架，**只新建文件、不覆盖任何已有文件**，重复 init 会拒绝：
```
$ agenttest init --dir my-repo
已在 my-repo 生成骨架：
  + my-repo/.agenttest/README.md
  + my-repo/.agenttest/asserts.txt
  + my-repo/tests/test_agent_behaviour.py
下一步：
  1) agenttest record runs/latest -- python -m your_agent "your task"
  2) AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py
```
4 条测试锁住三个安全属性：生成三个文件、二次 init 拒绝、**已有测试文件绝不覆盖**（那条专门写了「先放一个自己的测试文件，init 必须失败且文件内容不变」）。

数字：三仓 0 star；Traffic 0；239 passed
## 2026-10-24（自循环第 12 轮）

产出：`docs/CASSETTE-SPEC.md` 增加「附录 A · 已知实现」+ 一条命令跑完整条互操作链（commit `f6340e7`，239 passed）。

四种实现被列成矩阵（写/读/校验/是否依赖本项目）：主实现 Python、参考实现 Node（**不 import 本项目**）、独立读取器（**import 白名单只有 5 个标准库**）、GitHub Action 包装（在第二个仓库真跑过）。

实测链路（三者互不共享代码）：
```
$ node examples/emit-node/emit.mjs /tmp/from-node      → wrote 6 records
$ python tools/reference_reader.py .../cassette.jsonl  → OK 6 条记录
$ python tools/validate_cassette.py /tmp/from-node     → PASS: 1/1 个 cassette 通过校验
```

同时写清了它**没**证明什么：事件序列的语义合法性（校验器只查结构与链）、跨语言浮点极端情况、source-map 等上层问题。这一节比「我们支持跨语言」这种话有用——它给出了可复现的验证方式，也划清了边界。

数字：三仓 0 star；Traffic 0；239 passed
## 2026-10-24（自循环第 13 轮 · 陌生人测试）

做法：新建一个只会算订单总额的小仓库（`agent.py` + `orders.jsonl`），假装自己从没听过 agenttest，按 README 的顺序走一遍并计时。

**第一次走，卡死了。** 两个真问题：
1. `init` 生成的下一步写着 `agenttest record ...`，但 `record` 要求 agent 用 `agenttest.agent.Session` 说话。陌生人照做 → `ERROR 没录到任何事件`。**我们让自己产品的第一屏指示走了条死路。**
2. 就算改用能跑的 `record-subprocess`（进程层观测，2 个事件），骨架里那条 `before:quote_error` 也会红 —— 因为进程层观测根本看不到 `model.result`。陌生人会以为是自己搞错了。

修法（commit 见 git log，239 passed）：
- 骨架首推 **record-subprocess**（任何 CLI agent 不用改代码），`record` / `import` 降为另外两条路径，并写清各自能观测到什么；
- 那条行为断言加 **skip 守卫**：cassette 里没有 `model.result` 就 `pytest.skip` 并说明原因 —— 绿着，但把差异讲清楚；
- `init` 的 next 步骤同步改成 record-subprocess。

第三次走（修完）：
```
$ agenttest init && agenttest record-subprocess runs/latest -- python agent.py && pytest
2 passed, 1 skipped in 0.02s        TOTAL elapsed=1s
```

耗时记录：init <1s、record-subprocess <1s、pytest 0.02s。**「5 分钟接入」这个目标现在是 1 秒级的，卡点不在时间而在指示错误** —— 这就是为什么必须假装陌生人走一遍，光看文档看不出来。
## 2026-10-24（自循环第 14 轮 · dogfood）

产出：`tools/dogfood.py` + 接进 ubuntu 与 windows 两个 CI job（commit 见 git log）。它用**真实命令**走一遍「不稳定断言 → 噪声分栏」的工作流，并断言四件事：
```
DOGFOOD OK
  噪声条数      1
  硬退步条数    0
  终端提示      有
  HTML 噪声节   有
```

为什么需要它：`flaky` 和 `regress --flaky-report` 之前只有单元测试各自为政，**没有一条命令证明它们连起来在真实仓库里是活的**。现在每次 push 两个平台各问一次。

判据写死在脚本里：已知不稳定的断言**不许**出现在 `newly_failing`（否则 fail）、噪声栏**不许**为空（否则 fail）、终端必须有那句「被分栏而不是被隐藏」、HTML 必须有噪声那一节。这样「功能退化」会红，「功能被悄悄删掉」也会红。

数字：三仓 0 star；Traffic 0；239 passed；dogfood 本机 exit 0
## 2026-10-24（自循环第 15 轮 · 单文件查看器）

产出：`tools/cassette_view.py`（243 passed）。把一份 cassette 变成**单文件离线 HTML**，双击就能看：
```
$ python tools/cassette_view.py examples/good
已生成 examples/good/view.html（20 条记录，7081 字节）
```

四条设计取舍（都是为了不骗人、不卡死）：
1. **零外部依赖**：生成的页面不引用任何 CDN —— 测试里直接断言 `http://` 与 `https://` 都不出现；
2. **不一次性铺 DOM**：只渲染前 500 行，搜索/滚动按需追加；
3. **哈希链当场重算**，断了就把**第一个断点的行号**放页面最上面并 exit 1（实测：改动第 6 条的 `t` → `警告：哈希链在第 6 行断了`）；
4. **`meta.unobserved` 必须显示**，而且缺了要说「没记」，不许说成「都观测到了」——这条专门写了测试。

软上限 30000 条 / 24MB 时截断（页面上明说截断了），>500MB 直接拒绝并告诉你去用 grep/jq 切片。

数字：三仓 0 star；Traffic 0；243 passed
## 2026-10-24（自循环第 16 轮 · README 一屏入口）

产出：README 重排（243 passed）。原来「License / MIT」被夹在正文中间、「遇到这些症状时」在最后一行，而 `init` / `plan` / `flaky` / `export` / `emit` / 查看器这些新东西一个都没写进去。现在前 40 行是：一句话是什么 → `demo` 自证输出 → **60 秒接入三条命令** → 症状表 → 命令一览（11 条，含各自「什么时候用」）。

11 条相对链接全部验过存在（脚本扫 `](./...)` 并逐个 `exists()`）。

**一次不可复现的红，记录在此**：改完 README 第一次跑全量时 `test_broken_chain_is_loud_and_exits_nonzero` 红了一次；单跑它绿，随后连续两次全量 243 passed。按我们自己的规则，这属于「n 小、不能下结论」——先记为环境性抖动，若下一轮再出现，就用 `agenttest flaky` 的思路去量化它，而不是靠记忆判断。

数字：三仓 0 star；Traffic 0；243 passed
## 2026-10-24（自循环第 17 轮 · 把「抖动」量化，然后它不是抖动）

上一轮我记了一条「不可复现的红」。这一轮按我们自己的规则先量化：同一条测试连跑 10 次。

**10 次全红。** 它不是抖动 —— 之前那次「两次全绿」是因为我机器上设了 `PYTHONIOENCODING=utf-8`，而测试用子进程跑时没有这个变量。

根因（用户可见的真 bug）：`tools/cassette_view.py` 没把 stdout 钉成 UTF-8。Windows 控制台默认 cp936，父进程按 utf-8 解码就是乱码，于是「哈希链在第 6 行断了」这种提示对任何按 UTF-8 读的调用方都是天书。仓库里 `tools/validate_cassette.py` 早有 `_force_utf8()`，注释里甚至写着「Linux CI 看不出来，Windows 上一 clone 就红」——**新加的查看器漏抄了这一段**。

修法：给查看器补同样的 `_force_utf8()`，并加一条回归测试 —— 显式剥掉 `PYTHONIOENCODING` / `PYTHONUTF8` 跑子进程，按 UTF-8 解码，断言中文提示真的能读。

结果：`10 次里失败 0 次`，244 passed。

教训写在 DAILY 里：**「一次绿」不构成证据，就像我们不能用 5 次全过主张稳定。** 上一轮我把它记成环境抖动是诚实的；这一轮跑 10 次把它证伪，也是同一套规则在起作用。
## 2026-10-24（自循环第 18 轮 · 同一个坑的横向排查）

上一轮修了查看器的编码 bug 之后，这轮把仓库里**所有会打印中文的入口**扫了一遍（脚本：非 ASCII + `print(` + 是否有 `_force_utf8`）。

结果 5 个候选里 1 个仍有问题：`tools/dogfood.py` —— 它打印「噪声条数 / 硬退步条数」，但从没钉过 UTF-8。CI 日志和任何按 utf-8 读的父进程都会看到乱码，而**本机带 `PYTHONIOENCODING` 时看不出来**（正是上一轮骗过我的那个变量）。

`src/agenttest/__main__.py` 经检查无需处理：它只调 `cli.main()`，而 cli 自己已经钉了编码。

修法两层：
1. 给 `dogfood.py` 补 `_force_utf8()`，实测剥掉 `PYTHONIOENCODING`/`PYTHONUTF8` 后中文仍可读；
2. 加 **lint 测试** `tests/test_encoding_guard.py`：任何 `tools/*.py` 只要含非 ASCII 且 `print(`，就必须出现 `_force_utf8` 或 `reconfigure(encoding="utf-8")`。另有一条行为测试真的剥掉环境变量跑一遍 dogfood 再按 utf-8 解码。

数字：三仓 0 star；Traffic 0；246 passed

为什么这条值得单独一轮：**同一个坑已经踩了三次**（validate_cassette 之后，cassette_view 和 dogfood 各漏一次）。第三次之后不该再靠「我记得」，只能靠规则 —— 这就是 lint 测试存在的理由。
## 2026-10-24（自循环第 19 轮 · 让页面能被找到）

前 18 轮基本都在内部打磨。这轮做的是**曝光侧**唯一在我权限内的事：把内容整理成「能被检索到、能被引用」的形态。

产出：
1. **`llms.txt`**（仓库根）：给 AI 检索用的纯文本入口，把我们**不可替代的事实**压缩成五条 —— 磁盘格式是带 sha256 链的 JSONL、六种事件类型、断言语法、统计诚实的具体数字（n=5 只到 43%，≤1% 需 381 次）、四种已知实现。
2. **`docs/errors/index.md`**：三页错误排查的索引，症状 → 页 → 一句话答案，并给出通用的三步（先取证、再量化、最后才改）。
3. 三条测试：`llms.txt` 无死链、索引必须覆盖 `docs/errors/` 下所有页面、**`llms.txt` 里的统计数字必须等于代码里 `runs_needed(0.99)` 的结果**（防止文档写飘）。

为什么这件事值得做而别的没用：三个仓 0 star / Traffic 0，最可能的机制不是「代码不够好」，而是**没有入口**。`llms.txt` 是当前成本最低、最可能被自动抓取的入口；错误页是唯一会被「人的搜索行为」命中的内容。

同时诚实记录：**这只是把门擦干净，不等于有人敲门。** 如果两周后 Traffic 仍是 0，说明问题不在这层，得换假设。

数字：三仓 0 star；Traffic 0；249 passed
## 2026-10-24（自循环第 20 轮 · 让所有主张可复跑）

产出：`tools/verify_all.py` + 自动生成的 `docs/VERIFY.md`（251 passed）。

```
$ python tools/verify_all.py
PASS  demo 一条命令自证：好 cassette PASS、坏 cassette FAIL
PASS  坏行为必须被断言抓住（replay 非零退出）
PASS  校验器接受合规 cassette（12 条规则）
PASS  校验器拒绝被篡改的 cassette
PASS  Node 独立实现写出的 cassette 通过 Python 校验器
PASS  统计主张有确切样本量：失败率 <=1% 需 381 次运行
PASS  查看器当场重算哈希链，断链时非零退出
PASS  剥掉编码环境变量后，中文输出仍按 UTF-8 可读
结果：8 / 8 通过
```

为什么值得花一轮：前 19 轮攒下的断言全都散在聊天记录和 commit message 里 —— **等于没有**。现在每条都是「主张 → 命令 → 结果」，`docs/VERIFY.md` 由脚本生成（手改无效，另有测试锁结构）。

清单末尾专门写了**这份清单不覆盖什么**：完整测试套件、双平台差异、性能与规模。不写这一节，这份清单就会被当成全部证据 —— 那正是我们一直在批评的做法。

数字：三仓 0 star；Traffic 0；251 passed；verify_all 8/8
## 2026-10-25（自循环第 21 轮 · 补上自己承认的性能缺口）

`docs/VERIFY.md` 一直写着「性能与规模：没有基准测试」。这轮把它补上。

实测（30,000 条事件 / 7.5 MB，正好压在查看器软上限上）：
```
生成 cassette   0.33s
validate        0.54s
view            0.55s（生成 6.6 MB 单文件 HTML）
regress         1.10s（3 个 run × 30k）
flaky           1.07s
```

结论：**这个量级下没有任何一步需要优化**。瓶颈在浏览器渲染端，所以限制 DOM 窗口 500 行，而不是把数据再压一次。

产出：`tools/bench.py`（`--quick` / `--json` / `--n`）、`docs/PERF.md`（含「这份基准不证明什么」）、CI 两个平台各跑一次 `--quick` 冒烟（2,000 条事件 + 阈值），两条测试锁住阈值与文档里的数字一致（30,000 / 500 MB 必须与代码里的常量对得上）。

数字：三仓 0 star；Traffic 0；253 passed；bench 30k 全绿
## 2026-10-25（自循环第 22 轮 · 从看板下钻到事件）

产出：`regress --html --html-views`（256 passed）。之前看板只能看到「run-1 FAIL」，想知道它到底做了什么都得另开终端。现在每个 run id 都是链接，点进去是那一份 cassette 的事件浏览页。

一个必须记下的设计冲突：仓库里原有测试断言「HTML 报告是**单文件**」。这个承诺（`demo` 也依赖它：单文件、零依赖、离线可开）比下钻更重要，所以**下钻做成 opt-in**，默认仍只出一个文件。

```
$ agenttest regress examples --assert before:quote_error --out rep --html --html-views
报告        html -> rep\index.html
报告        run_views -> rep\runs
$ ls rep/runs
bad.html  good.html
```

三条测试锁住：链接存在且目标文件真的是自包含页（无外部 http）、`run_views` 进 report.written、以及**没有 tools/ 时看板照常出、只是没有链接**（用 monkeypatch 模拟只装了 wheel 的情况）。

数字：三仓 0 star；Traffic 0；256 passed
## 2026-10-25（自循环第 23 轮 · 文档与 CLI 不许分家）

产出：`docs/REGRESS.md` 补三节（噪声分栏的用法与规则、下钻链接、`plan` 的问代价方式），README 命令表补 `--html-views`。259 passed。

这一轮最有价值的是最后加的测试 `tests/test_docs_match_cli.py`：它扫文档里出现的所有 `--flag`，逐个去 `cli.py` 里找，找不到就红。

```
文档提到但 CLI 里没有的开关： <空>
```

为什么值得：文档写着一个不存在的开关，是比没写更糟的体验 —— 用户照着敲，得到 `unrecognized arguments`，然后开始怀疑整个工具。这和 R13 那个「init 指向 99% 用户用不了的录制路径」是同一类错误：**文档里的承诺必须能在代码里找到**。

另有两条：噪声三规则必须原文出现在文档里（只有 MIXED_OBSERVED 算噪声 / 证据不足不算免责 / 不给报告时行为不变），以及 README 命令表必须提到 `--flaky-report`、`--html-views`、`plan`。

数字：三仓 0 star；Traffic 0；259 passed
## 2026-10-25（自循环第 24 轮 · 上限行为不许静默）

产出：4 条针对查看器上限的测试（263 passed）。上限写在代码里不等于行为正确，这轮把它钉住：

| 测试 | 锁住什么 |
|---|---|
| 超过 30000 条 | 只读前 30000 条，`truncated=True`，**页面里出现「已截断」且带数字** |
| 正常规模 | 不许被标成截断（避免天天喊狼来了） |
| 超过硬上限 | 抛 `SystemExit`，消息里同时给出下一步（grep / jq） |
| CLI | 打印的记录数必须是 30000 这个真实值 |

为什么值得单独一轮：**「静默截断」是这个项目最不能接受的失败模式**。它会让人以为看完了全部证据，而实际上只看到前一部分 —— 这和「5 次全过就说稳定」是同一类错误：让数据看起来比实际更有说服力。

顺带验证了自己的测试成本：生成 30,500 条事件 + 跑完 4 条测试共 1.45 秒，可以放心留在默认测试集里，不必标 slow。

数字：三仓 0 star；Traffic 0；263 passed
## 2026-10-25（自循环第 25 轮 · 新功能弄坏了老承诺，就得自己说出来）

上一轮加 `--html-views` 之后我就发现一个隐患：**单文件承诺的用法是「把 index.html 拷走」**，而一旦带了下钻链接，拷走就全断。

这轮的处理不是在文档里加一句免责，而是**让页面自己说**：带 `--html-views` 时，首屏多一行

```
这一页链接到 runs/ 下的下钻页；单独拷走 index.html 会让这些链接失效 —— 要真正单文件就别加 --html-views。
```

不带 `--html-views` 时这一行**不出现**（测试直接断言 `下钻页` 三个字不在单文件版本里）——否则就变成天天喊狼来了。

过程记录：这次手改模板又漏了一个 `+`（第 770 行），`py_compile` 当场抓到。这已经是同一类手误的第 N 次，说明「改完立刻编译」这条纪律比任何工具都可靠。

数字：三仓 0 star；Traffic 0；264 passed
