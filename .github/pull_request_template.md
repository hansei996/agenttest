## 这个 PR 做了什么

<!-- 一句话。链接对应的 issue：Closes #N -->

## 证据（自述不算）

- [ ] 本机跑过：`pytest tests -q` → <!-- 贴真实输出 -->
- [ ] CI：<!-- run id + conclusion -->
- [ ] 新增行为有测试覆盖
- [ ] CHANGELOG 有条目（面向用户的改动才需要）
- [ ] 没碰边界之外的文件：<!-- 贴 git diff --stat -->

## 诚实性检查

- [ ] 观测不到的数据没有伪造（写进 `meta.unobserved` 而不是编）
- [ ] 样本不足时没有给出精确结论
- [ ] 失败信息能直接当 review 评论读，不是 `AssertionError`

## 备注

<!-- 任何偏离设计的地方，以及为什么 -->
