# 回归看板（v0.3）

一次 replay 只证明"这一次的行为"。agent 是不确定的：同一句话跑 10 次，可能 2 次不守规矩。
所以要看的是**多次运行**：跑 N 次 → 存成基线 → 下次改 prompt / 换模型后自动比对 → 谁退步了一眼看见。

## 1. 三个动作

```bash
# ① 先把 N 次运行变成 cassette（每次一个目录）
agenttest record --repeat 10 runs/base -- python -m my_agent "修复 src/auth.py 的崩溃"

# ② 出报告 + 存成基线（这份 report.json 就是下次的基线）
agenttest regress runs/base --assert before:quote_error --out baseline/ --html

# ③ 改完 prompt / 换完模型，再跑一遍，和基线比
agenttest record --repeat 10 runs/new  -- python -m my_agent "修复 src/auth.py 的崩溃"
agenttest regress runs/new --assert before:quote_error --baseline baseline/report.json --out report/ --html
```

`regress` **不会重放**，它只读 cassette 并跑断言，所以很快、也很确定。

## 2. 数据从哪来

`regress` 接受：

| 输入 | 含义 |
|---|---|
| `<dir>/cassette.jsonl` | 把 <dir> 当成一个 run |
| `<dir>/<run>/cassette.jsonl` | 每个子目录一个 run（`record --repeat` 产生的 `runs/run-1/…` 就是这样） |
| `<file>.jsonl` | 单个 cassette，run id 用文件名 |

**run id 是相对路径**（例如 `run-3`、`subset/run-3`）。基线比对按 `(run id, 断言)` 配对，
所以两次要给同样的目录形状、同样的 run id，否则会被当成"新增的 run"而不是"退步"。
被跳过的目录：以 `.` 开头的（`.git`/`.work`）与层级超过 3 层的。

## 3. 终端输出怎么读

```
regress runs/new — 2 次运行，1 条断言
  run      before:quote_error  tokens  耗时     工具  结果
  -------- ------------------- ------- -------- ---- ------
  run-1    PASS                6,800   0.016s   4    PASS
  run-2    FAIL(第4事件)        5,380   0.015s   4    FAIL
  通过率      1/2（50%）
  FAIL        run-2 / before:quote_error — 第 4 个事件
              FAIL before:quote_error — 期望在第一次 edit 之前出现引用报错，实际第 4 个事件就是 edit_file(src/auth.py)…

基线比对（基线 2 次运行 → 现在）
  新增失败    1 条
    - run-2 / before:quote_error（第一次失败在第 4 个事件）
  修好        0 条
  通过率      100% → 50%（-50 个百分点）
  成本        tokens 6,800 → 6,090 (-10%) · 耗时 0.016 → 0.015 (n/a) · 工具调用 4 → 4 (0%)
```

* **没通过率 100% 的那种"全绿"是假的**：通过率是 run 级别，1/2 就是有一半的运行不守规矩。
* `FAIL(第N事件)` 里的 N 直接来自 assertions 的失败文案（"第 N 个事件就是 …"），
  定位到事件为止，不用自己数。
* **新增失败** = 基线里这条断言是过的、现在是不过的 → 这就是退步；会标出第一次失败发生在第几个事件。
* **修好** = 基线里不过、现在过了。
* **成本** 是每次运行的平均 tokens / 耗时 / 工具调用数，`n/a` 表示基线是 0 没法算百分比。

## 4. 退出码（当门禁用）

| `--fail-on` | 何时非 0 |
|---|---|
| `newly_failing`（默认） | 有新增失败；**或所有 run 都失败**（没有基线时至少别当自己是绿的） |
| `any` | 任何一条断言失败 |
| `never` | 永远 exit 0（只报告，不拦人） |

另外：**任何 cassette 读不了**（坏 JSON、二进制、编码不对）一律 exit 1，并在表格里把那个 run 标成 `ERROR`，
不会静默跳过——不然"少了几个 run 所以全绿"就是假绿。

## 5. HTML 报告

`--out 目录 --html` 会生成 `<目录>/index.html` 和 `<目录>/report.json`：

* **单文件**：CSS 内联，没有 `<script>`、没有外部链接、没有 CDN，离线双击就能看；
* 内容：run × 断言 的表格、失败详情（含事件序号与完整断言文案）、基线 delta、成本表；
* `report.json` 就是下次的 `--baseline`，别删。

## 6. 在 CI 里当门禁

```yaml
name: agent-regression
on: [pull_request]

jobs:
  regress:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install -e .
      # 基线：从 main 上取上次的 report.json（示例用 artifact 或入库文件皆可）
      - uses: actions/download-artifact@v4
        continue-on-error: true
        with: { name: agenttest-baseline, path: baseline }
      - name: run the agent N times
        run: |
          agenttest record --repeat 10 runs/new -- python -m my_agent "修复 src/auth.py 的崩溃"
      - name: regress against baseline
        run: |
          agenttest regress runs/new \
            --assert before:quote_error --assert touched:src/auth.py \
            --baseline baseline/report.json \
            --out report/ --html \
            --fail-on newly_failing
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: agent-regression-report, path: report/ }
```

要点：
* 门禁只拦**退步**（`newly_failing`），不会因为"本来就有一半跑不准"把 PR 全堵住；
  但**所有 run 都失败**时照样拦。
* 基线要跟着主干走：把 `report/` 作为 artifact 存下来，或定期把 `report.json` 提交进仓库。
* `--html` 传成 artifact，失败时点开就能看到是哪几个 run、第几个事件开始崩的。

## 7. 与其它动词的分工

| 动词 | 回答的问题 |
|---|---|
| `replay` | 这一份 cassette 的行为对不对（确定、快） |
| `stat` | N 次运行的**成功率 / 成本**够不够（比例断言看置信区间） |
| `regress` | 这次相对**上次**，谁退步了、谁修好了（按 run × 断言 比对） |
| `diff` | 两份 cassette 的**行为差别**长什么样（工具序列、成本） |

## 6. 已知不稳定的断言：`--flaky-report`（别让噪声冒充退步）

看板有个相反的失败模式：**已知会抖的断言一旦失败，就被算成「退步」**。于是 CI 因为噪声变红，团队开始忽略红灯 —— 那比没有看板更糟。

```bash
# ① 先量化它抖到什么程度（这一步不能跳）
agenttest flaky runs/base --assert before:quote_error --out flaky.json

# ② 再让看板把它分栏，而不是当退步
agenttest regress runs/new --assert before:quote_error \
    --baseline baseline/report.json --flaky-report flaky.json --out report/
```

执行结果里会出现单独一栏：

```
基线比对（基线 1 次运行 → 现在）
  新增失败    0 条
  噪声失败    1 条（已知不稳定，不计入退步）
    ~ run-1 / before:quote_error（第 4 个事件）
  注意        本次失败全部来自已知不稳定断言（MIXED_OBSERVED），未阻止 CI —— 它们被分栏而不是被隐藏
```

**三条规则**（都写进了测试，不是口头约定）：

| 规则 | 为什么 |
|---|---|
| 只有 `MIXED_OBSERVED` 算噪声 | `INSUFFICIENT_RUNS`（样本不够）**不是**免责理由；证据不足 ≠ 可以排除 |
| 噪声被排除时必须打印那句提示 | 「已知不稳定」不能变成「悄悄忽略」 |
| 不给 `--flaky-report` 时行为一字不变 | 这条功能是加法，不是改默认 |

## 7. 人工复盘：从看板下钻到事件

```bash
agenttest regress runs/new --assert before:quote_error --out report/ --html --html-views
#   报告 html      -> report/index.html
#   报告 run_views -> report/runs
```

每个 run id 都会变成链接，点进去是那一份 cassette 的事件浏览页（哈希链重新算过、`meta.unobserved` 会显示）。

**注意这是 opt-in**：不加 `--html-views` 时仍然只出一个 `index.html`，保持「单文件、零依赖、离线可开」的承诺。没有 `tools/` 的部署（只装了 wheel）会自动跳过下钻，看板照常出。

## 8. 先问代价：`plan`

```
$ agenttest plan
  目标下界   需要次数   可排除失败率
  0.90       35         > 10%
  0.99       381        > 1%
```

打算说「它很稳定」之前先跑这条：**想主张失败率 ≤10%，就得跑 35 次并全部通过。**
没有这个样本量时，任何「它很稳定」都只是点估计。
