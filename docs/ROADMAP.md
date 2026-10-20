# ROADMAP

> 一条主线：**让 agent 的行为像代码一样可以被测、被 diff、被回归。**
> 每一个版本必须能独立演示，且必须带一个可复现的数字。

## v0.1 — 能跑（已完成）
- 6 类事件的 cassette（JSONL + sha256 哈希链）
- replay：模型响应固定、网络守卫、确定性验证
- 断言：`before:` / `tool:` / `never:` / `touched:` / `exit:`
- diff：新增 / 缺失 / 顺序 / 成本四类
- 39 个测试，CI 绿

## v0.2 — 能用（进行中）
- [x] 可安装：`pip install` 后直接 `agenttest` 命令（去掉 PYTHONPATH）
- [x] 统计断言：`record --repeat N` + `stat`，成功率 / 成本 / 耗时；N<5 时必须警告
- [x] 日志导入器：OpenAI / Anthropic 现有日志 → cassette
- [ ] `agenttest import` 子命令接线（lead 负责）
- [ ] ROADMAP / CHANGELOG 落盘
验收数字：装好后三条命令（record / replay / stat）在一台干净机器上可跑通，CI 绿。

## v0.3 — 能接真东西
- 适配器：任意 CLI agent（子进程）+ 一个 HTTP agent 框架（择一）
- cassette schema 版本号 + 向后兼容策略（`schema_version` 字段 + 迁移说明）
- `agenttest init`：在现有仓库里生成最小测试骨架
验收数字：用 agenttest 给 **read-the-logs-first** 技能写出一条真实的回归用例，并在 docs/CASE-STUDY.md 给出运行记录。

## v0.4 — 能让行为变化被看见
- 产物级 diff（文件内容差异，而不只是"变没变"）
- 行为签名（tool call 序列的最小编辑距离）与阈值告警
- 与 pytest 集成：`pytest --agenttest`
验收数字：换一个模型/prompt 后，diff 能稳定指出"少了哪一步"，连续三次结果一致。

## v0.5 — 统计上站得住
- 置信区间与最小样本量建议（不是拍脑袋的 N≥5）
- 分层采样：按工具调用数 / 时长分层
- 失败归因：把失败的 run 聚成类别
验收数字：在 20 次采样下，给出"成功率 95% CI"，并证明与重复实验吻合。

## v1.0 — 成为规范
- 把 cassette 格式写成独立 spec 文档（别人可以实现兼容工具）
- 至少一个第三方实现（哪怕是脚本）能读写同一份 cassette
验收数字：spec 文档 + 一个独立的第三方读写示例。

---

## 不做（v1.0 之前）
- 不做 UI
- 不做模型质量评测（那是另一件事）
- 不做云服务
