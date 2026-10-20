# CHANGELOG

## v0.3.0
- **录制真实 CLI agent**：`agenttest record-subprocess <dir> -- <cmd>`，两种事件来源（agent 自输出 JSONL / 进程层观测）。观测不到的事件写进 `meta.unobserved`，**不伪造**；agent 自报的 run.start/run.end 一律丢弃，`argv`/退出码只认观测值
- **文件改动**：前后 sha256 快照（不依赖 git），增/改/删都记；>5000 文件记 `meta.snapshot_capped` 而非静默截断
- **argparse 陷阱**：`record-subprocess` 在第一个 `--` 处切分，选项放在位置参数前后都能用（`record` 的解析路径未动）
- **回归看板**：`agenttest regress` 把 N 次运行的断言结果汇成一张表；`--baseline` 比对给出新增失败 / 修好 / 通过率与成本 delta，并标出第一次失败发生在第几个事件；`--html` 生成**单文件零依赖**报告（实测 0 个 `<script>`、0 个外链）；`--fail-on newly_failing|any|never` 可直接当 CI 门禁
- **regress 不重放**：只读 cassette + 跑断言，快且确定；坏 cassette 标 `ERROR` 而不是静默跳过，避免「少了几个 run 所以全绿」

## v0.2.0
- **打包**：新增 `pyproject.toml` 与 `agenttest` 入口，安装后不再需要 `PYTHONPATH=src`
- **统计断言**：`record --repeat N` 产出 `batch.jsonl`；`stat` 子命令判定 `success>=X` / `tokens<=Y` / `duration<=Z`，小样本（N<5）强制警告
- **日志导入器**：`agenttest.importers.load()` 支持 OpenAI Chat Completions 与 Anthropic Messages 两种日志格式，映射为 6 类事件；缺失时间戳会合成并在 `meta.warnings` 留痕
- **统计诚实性**：比例断言改为按 95% 置信区间判定（`>=` 看下界、`<=` 看上界）；点估计够但区间不够时默认 **FAIL**，须显式加 `--point-estimate` 才按点估计通过，并在报告里标注「非统计显著」
- **cassette 规范**：新增 `docs/CASSETTE-SPEC.md`、`docs/cassette.schema.json` 与 `tools/validate_cassette.py`（纯标准库），第三方可据此实现兼容工具
- **`agenttest import` 子命令**：`import <log> <outdir> [--format auto|openai|anthropic] [--exit-code N]`，把日志写成 cassette 并打印格式/事件计数/时间戳来源/warnings；导入的 cassette 明确提示不可 replay
- **BOM 与编码**：读取容忍 UTF-8 BOM（写出仍不带 BOM、不再产生 CRLF）；UTF-16 / 二进制 / 非法 UTF-8 / JSON 坏掉四类错误各自给出可操作建议，不再甩 `Unexpected UTF-8 BOM`
- **独立实现**：`tools/reference_reader.py` 不 import agenttest，独立校验链与必填字段；规范公布的三段示例喂给它全部通过
- **文档**：ROADMAP、本 CHANGELOG、`docs/CASE-STUDY.md`（如何用一个测试框架给技能写回归）、`docs/CASSETTE-SPEC.md`、`docs/IMPORTERS.md`、`docs/PYTEST.md`；根目录 `.gitignore` 挡住 `__pycache__`/`*.egg-info`

### 本版修掉的三个真实缺陷（都是 CI 全绿也发现不了的）
1. **统计断言把「没证据」判成「证明了」**：n=3 全成功时 `success>=0.99` 曾判 PASS。现在按 95% 置信区间判定，默认 FAIL，需 `--point-estimate` 才按点估计放行。
2. **校验器输出 cp936 乱码**：Linux CI 永远是 UTF-8，Windows 上子进程捕获即乱码。现强制 UTF-8 输出，测试主动摘除 `PYTHONIOENCODING` 以免依赖外部环境。
3. **带 BOM 的合法 cassette 被判非法**：一个 BOM 会让 4 条规则同时红，用户只会以为数据坏了。现读取容忍、写出禁止。

## v0.1.0
- 首个可用版本：cassette（JSONL + sha256 哈希链）、确定性 replay（网络守卫）、5 类断言、四类 diff
- 39 个测试；GitHub Actions 跑绿

---

格式参考 Keep a Changelog；版本号语义化。