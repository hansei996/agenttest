# 提交包：read-the-logs-first v2（待维护者回话后即可发出）

> 背景：`github/awesome-copilot` 的 PR #5256 被关闭，理由是「这十条规则描述的是模型本来就会做的事……模型不知道的调试知识或能确定性提取出错帧的脚本，才是强得多的贡献」。
> 本文件记录针对该意见做的 v2 及**本地已通过的校验证据**。是否重提，等维护者回话（我们已在 #5256 下询问）。

## v2 改了什么

| 意见 | v2 的做法 |
|---|---|
| 规则是模型已经会的事 | 规则从「十条行为要求」降到第二位；第一屏换成两条**模型不会自己产出**的内容 |
| 需要确定性地提取出错帧 | 给出**可执行规则**：Python traceback 从外到内 → 最内层用户帧是**最后一个**；V8 stack 从内到外 → 是**第一个**；并明确跳过 `site-packages` / `node_modules` / `node:internal` / stdlib。工具 `tools/extract_frame.py` 只是这条规则的实现（找不到用户帧就 exit 2，不猜） |
| 需要运行时特定的日志位置 | 新增表格：pytest 的 capture 与 `-s`、Python logging 走 stderr、`docker logs` vs `docker inspect`（OOM=137）、`journalctl -u`、GitHub Actions 的 step log vs annotation、nginx `error.log` vs `access.log` |
| 可移植性 | SKILL.md 现在**自包含**：不依赖仓库里有 `tools/`，规则本身即是算法；工具作为可选实现提及 |

## 本地校验证据（在他们自己的 clone 里跑）

```
$ npm run skill:validate
✅ All 441 skills are valid
🎉 Skill validation passed          exit 0

$ npm run build
✓ Successfully generated marketplace.json with 182 plugins (104 local, 78 external)

$ git diff --numstat
1  1  docs/README.skills.md
38 21 skills/read-the-logs-first/SKILL.md
```

生成的表格行（机器生成，未手改）：

```text
| [read-the-logs-first](../skills/read-the-logs-first/SKILL.md)<br />`gh skills install github/awesome-copilot read-the-logs-first` | Use when debugging a failure, a broken test or CI run, or when the user pastes a traceback. Gives the agent two things it would otherwise guess at - a deterministic way to pick the failing frame out of a traceback, and where each runtime actually writes its logs - then rules for changing one thing at a time. | None |
```

分支已在我们 fork 本地准备好（clone：`_awesome_copilot2`，分支 `add-read-the-logs-first-skill`，commit `b328c9c`），补丁：`DSH_workspace/.awesome-rlsf-v2.patch`（19,374 字节）。

## 待办（等一个条件）

- [ ] 维护者在 #5256 回话表示欢迎重提 → 推送分支 + 开 PR（正文已备好，见下）
- [ ] 若无回话，**不重复提交**：改为把同一份内容贡献给其他清单（BehiSecc #1010 仍在审）

## 备用 PR 正文

```
v2, following your review on #5256.

You said the ten rules describe what models already do, and that the contribution
should carry knowledge a model does not have. This version leads with two such things:

1. A rule for picking the failing frame that a model reliably gets wrong: a Python
   traceback is outermost-first so the innermost user frame is the LAST one, while a
   V8 stack is innermost-first so it is the FIRST one; stdlib / site-packages /
   node_modules / node:internal are skipped. The bundled extractor is that rule as code
   and exits 2 rather than guessing.
2. A table of where each runtime actually writes logs (pytest capture vs -s, docker logs
   vs inspect, journalctl, Actions step log vs annotation, nginx error.log vs access.log).

Declared self-contained: the SKILL.md no longer needs the repo's tools/ directory.
Validated with npm run skill:validate (441 skills OK) and npm run build (table regenerated).
```
