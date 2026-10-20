# 实现说明与对 DESIGN.md 的偏离（v0.1）

## 新增字段（additive，不改已有语义）

DESIGN 第 1 节给了 6 类事件的样例字段，实现时补了三个字段让第 3 节的承诺可执行：

| 事件 | 新字段 | 为什么 |
|---|---|---|
| `run.start` | `workdir` | DESIGN 第 3 节要求"结束时对比实际改动 == 记录改动"，得知道去哪比对。按相对 cwd 记录，换机器仍可解析。 |
| `run.end` | `files` | 只有文件名（`files_changed`）无法判断"改动是否一样"，所以同时记录每个产物的 sha256。 |
| `tool.call` / `model.result` | 沿用原有字段 | 无变化：`model.call.request` 里存完整的 `messages` / `tools` 列表，而不是示例里的字符串占位。 |

## `stat:` 断言：改成 batch 侧实现（v0.1 之后的一次修订）

原先 `stat:` 在单次 replay 里直接 FAIL 说"未实现"。现在它有了真实实现，但落点在
**批量运行**上，因为单次 replay 是确定的，成功率恒为 1 或 0，在那里算"成功率"只会骗人：

- `agenttest record --repeat N` 跑同一任务 N 次，把每次运行的摘要写进 `batch.jsonl`
  （成功与否、tokens、耗时、工具调用数），每次的完整 cassette 留在 `runs/run-<i>/`。
- `agenttest stat batch.jsonl --assert "success>=0.8" --assert "tokens<=2000"`
  打印每个统计量的实测值与判定，并给出成功率的 Wilson 95% 置信区间。
- **样本 < 5 时一定打 WARN**（给出置信区间，说明别当精确值）。

### 修正：比例断言不许用点估计冒充结论

第一版把 `success>=X` 拿点估计直接比，于是 n=3 全成功（点估计 1.00，95% 区间 0.44–1.00）
对 `success>=0.99` 判了 PASS 并 exit 0——这是把"没证据"说成"证明了"，正是这个工具最该防的错。现在：

- `success>=X` 用 95% 置信区间**下界**判定（`<=X` 用上界，`==` 要求区间退化）；
- 点估计够、边界不够 → **默认 FAIL**，输出同时给点估计、区间、下界，并写明"样本不足，无法证明该阈值"；
- 逃生口 `--point-estimate` 才允许 exit 0，且报告顶部与该条断言都标注"按点估计通过，非统计显著"；
- `tokens` / `duration` / `tool_calls` / `runs` 是确定性量，仍按实测值判定。

数字对照（Wilson，z=1.96）：n=3 全成功 → 下界 0.44；n=5 全成功 → 下界 0.57。
所以 n=5 时 `success>=0.5` 能过、`success>=0.8` 不能，测试与 CI 都按这个真实区间写。

另：所有运行的 `duration` 都是 0.000s 时（没有真实 I/O 的假 agent），报告会显式提示该统计量无意义。

因此 `replay --assert stat:...` 仍然是"这里不适用"，会明确指向 `agenttest stat`，
不再假装是"未实现"。

## 打包

根目录新增 `pyproject.toml`（setuptools 后端，`dependencies = []`，console script
`agenttest = agenttest.cli:main`）。这意味着写入范围扩大到仓库根，README 首屏结构不变，
只在运行示例块里加了一行安装命令；CI 增加 `pip install -e .` 与"无 PYTHONPATH 跑 console script"两步。

`pip install -e .` 会把启动器写到当前解释器的 Scripts/bin 目录；该目录不在 PATH 上时要自行加上。

## 历史：`stat:` 断言曾经未实现

DESIGN 第 4 节列了 `stat:success>=0.8,n=20`。v0.1 明确不实现，执行到会返回
`FAIL stat:... — v0.1 未实现统计断言`。

理由：统计断言需要跑 N 次真实运行（record 侧），而 replay 是确定的——同一份 cassette
重放 N 次成功率恒为 1 或 0，把它写成"通过"只会骗人。它属于"批处理 + 采样"，
不是 v0.1 的范围。

## diff 只输出四类

DESIGN 第 5 节的要点里提到了"产物：文件级 diff"，但同一节的输出示例只有四行
（新增 / 缺失 / 顺序 / 成本）。v0.1 按输出示例实现四类，产物差异由
`touched:` 断言和 `run.end.files` 的哈希校验负责，不重复出现在 diff 里。
四类即使为空也会输出（显示"（无）"），保证结构化输出形状稳定。

## replay 的文件系统起点

DESIGN 第 3 节写的是"先用 cassette 的 files_changed 建立初始快照"。
v0.1 的做法是：agent 自己把工作目录从模板恢复（`examples/app` -> `examples/.work/<script>`），
harness 在 replay 结束后独立重算 `run.end.files` 里每个产物的 sha256 并要求相等。
初始状态由模板决定而不是由 cassette 回放，简化了 v0.1，但仍然能在产物漂移时失败。

## 跨机器重放

`run.start.argv` 里解释器记成占位符 `python`（replay 时解析成当前解释器），
agent 脚本记成相对 cwd 的路径；`replay` 找不到录制机器的 cwd 时，
会从 cassette 目录往上找"相对路径能成立"的那一层。因此同一份 cassette
在 Windows 录制、在 ubuntu-latest 上也能重放（CI 就是这么跑的）。

## 环境说明

仓库没有根目录的 `pyproject.toml` / `setup.py`：v0.1 的写入范围只有
`src/` `tests/` `examples/` `docs/` `.github/`。因此 CLI 需要 `PYTHONPATH=src`
（或在 `src/` 目录内运行），`tests/conftest.py` 会自己把 `src/` 加进 `sys.path`。

## 导入器（importers）：DESIGN 里没有的第七件事

DESIGN 只描述"跑一次 -> 事件流"，没有"把别人已有的日志读进来"这条路。
v0.1 补了 `src/agenttest/importers/`（用法见 docs/IMPORTERS.md），三条偏离记在这里：

1. **`run.start` 多一个 `meta` 字段**（`format` / `source` /
   `synthetic_timestamps` / `warnings`）。这是 additive：`events.validate`
   只校验必填字段，`diff` 只比较工具调用与模型输出，既有语义不变。加它的理由是
   "合成时间戳"和"读不懂的内容"必须留在 cassette 里可核验，而不是只在内存里返回一次。
2. **导入的 cassette 不可 replay**：`run.start.argv` 是 `[]`，`cwd` 是 `.`，
   `env_fingerprint` 是 `imported|<格式>`。日志里没有 agent 可跑，所以不假装它
   能重放；导入的 cassette 用来读、diff、跑断言，要 replay 得把 argv 指向自己的 agent。
3. **时间戳策略是 DESIGN 没定义的**：只要有一轮缺时间戳，就把**全部** `t` 按事件
   序号合成（`index * 0.1`），同时在 `meta` 里标记并写 warning。真实与合成不混用，
   避免把合成值混进真实时间。
