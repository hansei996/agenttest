# 可复跑的验证清单

> 这份文件由 `python tools/verify_all.py --write-doc` 生成，不要手改。
> 每一条都是「主张 → 命令 → 结果」，谁不信就自己跑一遍。

当前结果：**8 / 8 通过**

| # | 主张 | 复跑命令 | 结果 |
|---|---|---|---|
| 1 | demo 一条命令自证：好 cassette PASS、坏 cassette FAIL | `python -m agenttest demo` | PASS |
| 2 | 坏行为必须被断言抓住（replay 非零退出） | `python -m agenttest replay examples/bad --assert before:quote_error` | PASS |
| 3 | 校验器接受合规 cassette（12 条规则） | `python tools/validate_cassette.py examples/good` | PASS |
| 4 | 校验器拒绝被篡改的 cassette | `python tools/validate_cassette.py <被改过一个字节的副本>` | PASS |
| 5 | Node 独立实现写出的 cassette 通过 Python 校验器 | `node examples/emit-node/emit.mjs <dir> && python tools/validate_cassette.py <dir>` | PASS |
| 6 | 统计主张有确切样本量：失败率 <=1% 需 381 次运行 | `python -c 'from agenttest.flaky import runs_needed; print(runs_needed(0.99))'` | PASS |
| 7 | 查看器当场重算哈希链，断链时非零退出 | `python tools/cassette_view.py <被篡改的 cassette>` | PASS |
| 8 | 剥掉编码环境变量后，中文输出仍按 UTF-8 可读 | `python tools/dogfood.py   （不设 PYTHONIOENCODING）` | PASS |

## 这份清单**不**覆盖什么

- 完整测试套件（`python -m pytest tests -q`）——它本身就是证据，不重复列。
- Windows 与 Linux 的差异：CI 两个平台各跑一次，看 Actions 记录才算数。
- 性能与规模：见 [docs/PERF.md](./PERF.md)（30k 事件四条路径的实测耗时与上限说明）。
