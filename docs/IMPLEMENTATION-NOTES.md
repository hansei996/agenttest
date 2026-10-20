# 实现说明与对 DESIGN.md 的偏离（v0.1）

## 新增字段（additive，不改已有语义）

DESIGN 第 1 节给了 6 类事件的样例字段，实现时补了三个字段让第 3 节的承诺可执行：

| 事件 | 新字段 | 为什么 |
|---|---|---|
| `run.start` | `workdir` | DESIGN 第 3 节要求"结束时对比实际改动 == 记录改动"，得知道去哪比对。按相对 cwd 记录，换机器仍可解析。 |
| `run.end` | `files` | 只有文件名（`files_changed`）无法判断"改动是否一样"，所以同时记录每个产物的 sha256。 |
| `tool.call` / `model.result` | 沿用原有字段 | 无变化：`model.call.request` 里存完整的 `messages` / `tools` 列表，而不是示例里的字符串占位。 |

## 未实现：`stat:` 断言

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
