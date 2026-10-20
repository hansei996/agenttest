# ADAPTERS：让真实的 CLI agent 也能被录制

record 到现在只认得两种来源：用 agenttest SDK 说话的 agent（examples/fake_agent.py），
和导入的日志（docs/IMPORTERS.md）。**适配器**是第三条路：把任意一个 CLI agent 当成
黑盒子跑一次，把它这次运行里能观测到的一切录成 cassette。

```bash
agenttest record-subprocess cassettes/run1 -- python my_agent.py --task "fix the bug"

agenttest record-subprocess cassettes/run1 --cwd . --timeout 300 \
    --stream-limit 4000 -- python my_agent.py --task "fix the bug"
```

选项写在 `--` 前后都可以，命令本身写在 `--` 之后。Python 里直接用同一个入口：

```python
from agenttest.adapters import record_subprocess

outcome = record_subprocess(
    ["python", "my_agent.py", "--task", "fix the bug"],
    "cassettes/run1",
    cwd=".",
    timeout=300,
)
print(outcome.events_source)   # agent_stdout / os_observation
print(outcome.unobserved)      # 这次没观测到的事件类型
```

## 两种事件来源

### 1. `agent_stdout`：agent 自己吐事件

约定：**stdout 上每一个非空行都是 JSON 对象，且带 `type` 字段、能过事件校验**。
满足时，这些事件被直接采用（它们来自 agent 本人，是真实报告），适配器只负责补上
首尾两件事：`run.start` / `run.end`。

判定是**全有或全无**的：只要有一行不是 JSON、或者有一条事件字段不合法，整体退回
`os_observation`，并把原因写进 `meta.stdout_note`（例如"第 2 行不是 JSON"）。
不挑着用，是因为"挑出来的一半事件"没法说明另一半去哪了。

### 2. `os_observation`：只有进程层的观测

没有 JSONL 时，适配器只能看见进程边界外面的事实：

| 事实 | 从哪来 | 记在哪 |
|---|---|---|
| argv | 调用方给的 | `run.start.argv` |
| cwd | 调用方给的 | `run.start.cwd` |
| 退出码 | 进程返回值 | `run.end.exit_code`，`meta.exit_code` |
| 耗时 | 秒表 | `run.end.t`，`meta.duration_s` |
| stdout / stderr | 捕获（截断） | `meta.stdout` / `meta.stderr` |
| 被改动的文件 | 跑前跑后 sha256 快照取差集 | `run.end.files_changed` / `run.end.files` |
| **model.call / model.result / tool.call / tool.result** | **看不见** | 只出现在 `meta.unobserved` 里 |

因此 os_observation 产出的 cassette 通常只有 **2 条事件**（run.start + run.end）。
这不是偷懒，这是这次运行能诚实支撑的全部内容。

## 为什么不能假装观测到工具调用

一条 `tool.call` 声称"agent 在这一刻调用了工具 X，参数是 Y"。黑盒子进程不会告诉
我们这件事——我们能看到的只有它最后留下的文件、它打印的文字和它的退出码。

想"补全"看起来并不难：diff 里出现 `src/auth.py` 就猜一个 `edit_file(src/auth.py)`。
但那条事件描述的是**我们的猜测**，不是 agent 的行为。等以后行为真的漂移了（它改成
调用 `patch`、或者根本没调用工具），只要猜测规则没变，cassette 里那条假事件也不会变，
回归测试照样绿——于是这份 cassette 从"证据"退化成了"自证"。

所以这里的选择是：宁可交出 2 条事件 + 一份诚实的 `unobserved` 清单，也不交一份
看起来完整、实际靠猜的 6 类事件流。要真正记录工具调用，只有两条正路：
让 agent 用 agenttest 的 SDK 说话（`agenttest.agent.Session`），或者让它按上面的
约定在 stdout 上吐 JSONL。

## 文件改动为什么用 sha256 前后对比，而不是 git status

* **不要求在 git 仓库里**：很多 agent 在临时目录、挂载点、容器里工作，那里没有 `git`。
* **不依赖 git 的忽略规则**：`git status` 会把"上次运行留下的未跟踪文件"和"这次
  新生成的文件"混在一个未跟踪列表里，还得自己再分一次。
* **与 `run.end.files` 同一个哈希**：replay 的产物校验直接复用，不需要第二套口径。

代价：要看整个工作目录（跳过 `__pycache__`、`node_modules`、`.git` 这类目录），
文件数超过 5000 就停下，并把 `meta.snapshot_capped` 记成 true——不静默截断。

增、改、删都会被记下来：`run.end.files` 里被删掉的路径值是 `null`。

## meta 字段一览（`run.start.meta`）

| 字段 | 含义 |
|---|---|
| `cassette_kind` | 固定 `"subprocess_agent"` |
| `events_source` | `"agent_stdout"` / `"os_observation"` |
| `unobserved` | 这次没观测到的事件类型（有序，按事件白名单） |
| `stdout_note` | 为什么走这条分支（"stdout 是空的" / "第 2 行不是 JSON" / 采用了多少条自报事件） |
| `stdout` / `stderr` | 截断后的原文，`*_truncated` 标明是否截断，`stream_limit` 是上限 |
| `exit_code` / `duration_s` | 与 run.end 一致，方便只看头一条记录 |
| `files_observed` | `{"created","modified","deleted"}` 计数 |
| `files_detection` | 固定 `"sha256_before_after"` |
| `snapshot_files` / `snapshot_capped` | 快照扫了多少文件、有没有被 5000 上限截断 |
| `envelope_source` / `envelope_dropped` | 首尾事件由适配器写入；agent 自报的同类事件被丢弃的条数 |

`envelope_source` 是安全阀：agent 在 stdout 里自报一条
`{"type":"run.start","argv":["rm","-rf","/"]}` 不会污染 cassette——argv 与退出码永远
以观测为准（tests/test_adapters.py 里有一个专门伪造 envelope 的用例）。

## 超时与失败

`--timeout` 给的是上限秒数。超时后子进程会被杀掉，`record_subprocess` 抛
`AdapterError`（CLI 退出码 1），消息里写明超时值、实际跑了多久、以及怎么放大上限；
**不会**写出半份 cassette。命令不存在（`OSError`）同样是清晰的 `AdapterError`。

## 与 importers 的分工

| | importers | adapters |
|---|---|---|
| 输入 | 已有的模型日志文件 | 一次真实进程运行 |
| 事件来源 | 日志里写的 request/response | stdout 的 JSONL，或进程层观测 |
| 能不能 replay | 不能（没有可跑的 agent） | 能——`run.start.argv` 就是命令本身 |
| 关键诚实点 | 缺时间戳就标 synthetic | 看不见的事件写进 `unobserved` |

## 已知边界

* `os_observation` 的 cassette 里没有模型/工具事件，`--assert tool:...` 这类断言
  在它上面会直接失败——这正是 `unobserved` 想提醒的事。
* stdout 既是"事件流"又是"日志"的 agent 需要自己约定清楚；混着来会整体退回
  `os_observation`。
* 快照只覆盖一个目录（`--watch` 指定的那个），不覆盖 agent 写到别处的文件。
