# DESIGN

## 1. 核心抽象：事件流

一次运行 = 一个有序事件流。事件类型（v0 只有这 6 种，宁少不多）：

```json
{"t":0.0,"type":"run.start","agent":"my_agent","argv":["..."],"cwd":"/repo","env_fingerprint":"py3.12|linux"}
{"t":0.1,"type":"model.call","model":"x","request":{"messages":"...","tools":"..."}}
{"t":2.3,"type":"model.result","text":"...","tool_calls":[{"name":"read_file","args":{"path":"src/auth.py"}}],"usage":{"in":1200,"out":300}}
{"t":2.4,"type":"tool.call","name":"read_file","args":{"path":"src/auth.py"}}
{"t":2.5,"type":"tool.result","name":"read_file","ok":true,"bytes":812}
{"t":9.9,"type":"run.end","exit_code":0,"files_changed":["src/auth.py"]}
```

**为什么是事件流而不是"录制 HTTP"**：HTTP 层录制绑死协议；事件层能覆盖 CLI agent、本地模型、多进程工具。

## 2. cassette 格式

一行一个事件，JSONL，追加写，带 `sha256` 链（每条记录包含前一条的哈希）→ 检测篡改，也让 diff 可以按"第一个不同的位置"精确定位。

## 3. replay 的确定性契约

- `model.result` 由 cassette 提供，**顺序消费**；consumed 用尽而 agent 又发请求 → 直接失败（说明行为漂移）
- replay 期间拦截网络：注入 `socket` 守卫，任何真实出网都报错并指出调用栈
- 文件系统：先用 cassette 的 `files_changed` 建立初始快照，结束时对比"实际改动 == 记录改动"

## 4. 断言语言（v0，故意小）

```
--assert before:quote_error              先引用报错再改代码（事件序）
--assert tool:read_file(path=src/auth.py) 调用了某个工具与参数
--assert never:tool=delete_file          从未调用危险工具
--assert touched:src/auth.py             最终产物包含该文件
--assert exit:0
--assert stat:success>=0.8,n=20          统计断言（跑 N 次）
```

## 5. diff 语义

两次运行对比的是**行为**，不是文本：
- 工具调用序列的最短编辑距离（插入/删除/顺序变化）
- 产物：文件级 diff
- 成本：token/时间/工具调用次数的变化

输出形如：
```
行为差异 (before → after)
  + 新增  read_file(src/auth.py)      before 没有读文件就改代码
  - 缺失  quote_error                 before 会先引用报错
  ~ 顺序  edit → test 变成了 test → edit
  成本   tokens 1,200 → 2,100 (+75%)
```

## 6. 不做的事（v0）

- 不做模型质量评测（那是另一个问题）
- 不做 UI
- 不内置任何 agent 框架的适配器——适配器是插件
