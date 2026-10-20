# CHANGELOG

## Unreleased (v0.2)
- **打包**：新增 `pyproject.toml` 与 `agenttest` 入口，安装后不再需要 `PYTHONPATH=src`
- **统计断言**：`record --repeat N` 产出 `batch.jsonl`；`stat` 子命令判定 `success>=X` / `tokens<=Y` / `duration<=Z`，小样本（N<5）强制警告
- **日志导入器**：`agenttest.importers.load()` 支持 OpenAI Chat Completions 与 Anthropic Messages 两种日志格式，映射为 6 类事件；缺失时间戳会合成并在 `meta.warnings` 留痕
- **文档**：新增 ROADMAP、本 CHANGELOG

## v0.1.0
- 首个可用版本：cassette（JSONL + sha256 哈希链）、确定性 replay（网络守卫）、5 类断言、四类 diff
- 39 个测试；GitHub Actions 跑绿

---

格式参考 Keep a Changelog；版本号语义化。
