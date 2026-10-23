# 分发现状与规则

> 第一行写的教训：**我们曾把「建立机制」当成「机制在运行」**。定时卡报告 succeeded，实际两晚零产出。
> 所以本文件里的每个数字都必须来自一次真实读数，并附上读数时间。

## 1. Traffic 基线（唯一能证明「有没有人看见」的数）

```powershell
gh api repos/hansei996/<repo>/traffic/views
gh api repos/hansei996/<repo>/traffic/popular/referrers
```

| 日期 | read-the-logs-first | agenttest | blame-archaeology |
|---|---|---|---|
| 2026-10-21 | 0 views / 0 uniques / 无 referrer | 0 / 0 / 无 | 0 / 0 / 无 |

**判据**（来自团队讨论，非拍脑袋）：
- 无任何来源带来 >500 曝光、referrers 全空 → **分发错**（没人到达），换渠道，别改产品
- ≥300 独立访客但 star 转化 <1% → **包装错**（被看见了，承诺不成立），只改 README 首屏

## 2. 投放规则

1. **每个渠道只发一次**。HN/Reddit 的重复提交会消耗账号信用。
2. **发之前先过 5 分钟陌生人测试**：把自己当陌生人，从 README 第一行读起，5 分钟内不装、不看源码，能不能获得价值？不能就改到能为止。
3. **链接带 utm 或可识别参数**，让 star 簇能被解释——这是和刷量的唯一区别（可追溯来源）。
4. **作者必须在场**：发帖后 2 小时内逐条回复。定时发布只做备忘，不能替代在场。

## 3. 渠道记录（每次投放后更新）

| 日期 | 渠道 | 链接（带参数） | 当天 referrals | star 变化 | 结论 |
|---|---|---|---|---|---|
| — | 尚未投放 | — | — | 0 → 0 | — |

## 4. 已验证的机制（哪些真带量）

| 机制 | 是否需要账号 | 状态 |
|---|---|---|
| awesome 清单收录（ComposioHQ 77k / BehiSecc 10k / awesome-copilot 40k） | 否 | 2 个 PR 已提，1 个已关闭重开 |
| GitHub Actions Marketplace（`uses: hansei996/agenttest/validate@v1`） | 否 | action.yml 已补，待打 tag |
| 在「正在问这个问题」的 issue 里给真解答 | 否 | 未开始 |
| profile README（同名仓） | 否（可自动化） | 未开始，等首个 PR 合并后做 |
| pinned repos | **是**（无 API，只能网页点） | 不安排 |
| topics / 互链 / Discussions | 否 | topics 已补；后两者期望≈0，不做 |

## 5. 不会做的事

- 买 star、star 互换、群发 DM 求 star（社区先于算法识别，损失的是传播节点）
- 同一个技能开两条 PR
- 在没有 5 分钟陌生人测试通过前投放任何渠道
