# CASSETTE-SPEC

> **cassette 格式规范，schema 版本 `0.1.0`。**
>
> 这份文档的目标：让别人（另一个工具、另一种语言、另一个 agent 框架）能**读出并写出**
> 和 agenttest 一模一样的 cassette。读到这里的实现者不需要看 Python 代码。
>
> 权威顺序：**实现 > 本文件 > DESIGN.md**。本文每一处字段名、算法、事件名都从
> `src/agenttest/` 逐字核对过；凡是实现与 DESIGN.md 不一致的地方，以实现为准并已在
> 第 11 节标出。发现本文件与实现不符，是实现或本文件的 bug，不是"文档有自由度"。

---

## 1. 文件形态

一份 cassette 是**一个 UTF-8 文本文件**，通常命名为 `cassette.jsonl`。

| 约束 | 值 |
|---|---|
| 编码 | UTF-8，**不写** BOM |
| 结构 | JSONL：**一行一条记录**，记录之间用 `\n` 分隔 |
| 行尾 | 最后一条记录后面**有**一个 `\n` |
| 空行 | 读取时**忽略**（`line.strip()` 为空即跳过），写入时不产生 |
| 空文件 | **非法**。至少要有一条 `run.start` 和一条 `run.end` |
| 文件名 | 读取方接受目录（自动拼 `cassette.jsonl`）或直接给文件 |

一行**不能**跨行、不能有注释、不能包成 JSON 数组。需要打包多份 cassette 是外层的事，
与本格式无关。

参考实现的判据：扩展名以 `.jsonl` 结尾就当文件，否则当目录。

### 1.1 编码与 BOM

Windows 用户的记事本、PowerShell 的 `Set-Content -Encoding utf8`、以及不少编辑器默认会在文件开头写一个
UTF-8 BOM（字节 `EF BB BF`）。这一点足以让最朴素的读取实现当场失败，所以规范把它单独说清楚。

| 环节 | 规定 |
|---|---|
| **写出** | **MUST** 是 UTF-8，且**不带 BOM**（首字节不是 `EF BB BF`）。规范不允许"为保险起见加个 BOM"。 |
| **读取** | **SHOULD** 容忍开头的 UTF-8 BOM：有 BOM 与没 BOM 必须读到**同一份记录、同一个 hash**。 |
| **读取** | **SHOULD** 容忍每行行首多余的 BOM（多份文件拼接时常见）。 |
| **读取** | **MUST** 拒绝 UTF-16 / GBK 等非 UTF-8 编码，并给出**可操作**的建议（"另存为 UTF-8（无 BOM）"，或"用 `utf-8-sig` 读取"）。只说 `Unexpected UTF-8 BOM` 不算合格报错。 |
| **行尾** | LF、CRLF 以及两者混排都接受；空行忽略。 |
| **文件末尾** | 允许缺少最后一个换行。 |

**为什么写出去不许带 BOM**：`hash` 覆盖的是 `canonical({"seq","prev","event"})` 的字节（第 3.2 节）。
BOM 会变成第一条记录之前的额外字节，于是"内容完全相同、只差一个 BOM"的两份文件互校验不过；
而且 JSON 本身就不允许 BOM。**BOM 是读者的负担，不是写者的自由。**

**不可接受的"看着像 JSON"的形态**（要给得起人话）：

| 输入 | 报错必须说什么 |
|---|---|
| 整个文件是一个 JSON 数组 `[{...},{...}]` | "cassette 是 JSONL（一行一条记录），不是 JSON 数组" |
| UTF-16 存档 | "看起来是 UTF-16……请另存为 UTF-8（无 BOM）" |
| GBK / ANSI 存档 | "不是合法的 UTF-8……请另存为 UTF-8（无 BOM）" |

参考实现：`tools/validate_cassette.py` 与 `tools/reference_reader.py` 都用 `raw.decode("utf-8-sig")` 读入
（无 BOM 时与 `utf-8` 行为完全一致），解码失败时给出上面那几句人话。写出侧仍然是 `encoding="utf-8"`（不带 `-sig`）——
**只放宽输入，不放宽输出**。


---

## 2. 记录的键

每条记录是一个 JSON 对象，这四个键是必填的（其它键允许存在但会被忽略）：

| 键 | 类型 | 含义 |
|---|---|---|
| `seq` | 整数，从 `0` 起 | 本记录在文件里的序号，逐条 +1 |
| `prev` | 字符串或 `null` | 上一条记录的 `hash`；**第一条是 `null`** |
| `event` | 对象 | 事件本身，见第 4 节 |
| `hash` | 字符串 | 本条记录的 SHA-256，见第 3 节 |

**第一个记录的处理**：`seq` 为 `0`，`prev` 为 JSON 的 `null`（不是空字符串、不是 `0`、
不是省略这个键）。没有"创世哈希"常量——链的起点就是 `null`。

---

## 3. 哈希链：确切算法

这是整份规范里最需要逐字对齐的一段。

### 3.1 规范化 JSON（canonical）

记 `canonical(x)` 为：把 `x` 序列化成单行 JSON，满足

- 对象键按 Unicode 码点**升序**排序；
- 分隔符里逗号与冒号后面**没有空格**，也没有换行缩进；
- 非 ASCII 字符**原样输出**，不转义成 `\uXXXX`（`ensure_ascii=False`）；
- 数字按其最短往返表示（Python `json.dumps` 的默认行为；`0.1` 就写 `0.1`，不会写成
  `0.100000`）。

Python 里就是这一行，一字不差：

```python
json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

### 3.2 hash 覆盖的字节范围

被哈希的**不是整行**，而是**只有三个键的那个对象**：

```text
body = {"seq": <本行 seq>, "prev": <本行 prev>, "event": <本行 event>}
hash = lower_hex( sha256( canonical(body) 的 UTF-8 编码字节 ) )
```

要点：

- 算法：**SHA-256**，输出 **64 个小写十六进制字符**（`[0-9a-f]{64}`）。
- `hash` 字段本身**不参与**计算（否则自指，算不出来）。
- 行内的空白、键的顺序**不参与**计算——但 S6 要求整行恰好等于 `canonical(整条记录)`，
  所以实际上不能随便排版。
- `t` 在 `event` 里面，所以**改时间戳同样会断链**。

### 3.3 写出来的一行

写入时，整条记录（含 `hash`）也走同一个 `canonical`，所以磁盘上每一行都是规范化 JSON，
键序恒为 `event`、`hash`、`prev`、`seq`（字母序）。

### 3.4 一个可以手算核对的例子

第一条记录的事件是第 8 节的示例 1。被哈希的 174 个字节恰好是：

```text
{"event":{"agent":"demo_agent","argv":["python","demo_agent.py"],"cwd":"/repo","env_fingerprint":"py3.12|linux","t":0.0,"type":"run.start","workdir":"."},"prev":null,"seq":0}
```

对它取 SHA-256，得到：

```text
657f26acb5a27e6f33f0a58a4fd1742d2a62f04e5a961c4bd2740a2859bd66d1
```

这就是示例 1 第一行的 `hash` 字段。任何语言都能复现这一步；算出来的不是这个值，差异
一定在规范化（键序 / 空格 / 非 ASCII 转义）上。

### 3.5 链被破坏时会发生什么

| 篡改方式 | 会被哪条规则抓到 |
|---|---|
| 改某条的 `event`（不改 `hash`） | 该条的 S5：重算值不等于记录里的值 |
| 改某条的 `event` 并把该条 `hash` 也改成新算的值 | 下一条的 S4：它的 `prev` 仍指向旧哈希 |
| 删掉中间一条记录 | 断点处的 S3：`seq` 不再连续 |
| 调换两条记录的顺序 | 断点处的 S4 / S5 |

---

## 4. 事件

### 4.1 事件类型白名单（封闭的 6 类）

```text
run.start    model.call    model.result    tool.call    tool.result    run.end
```

**这个列表在 `0.1.0` 里是封闭的。** 不在列表里的 `type` 一律非法（S7），不会被"忽略"或
"跳过"。要新增类型必须升 `schema_version`（见第 6 节）。

### 4.2 必填字段

下表"必填"列的字段缺失即为非法（S8）。**注意：实现只检查字段是否存在，不检查类型**
（唯一例外是 `t`，见 S11）——所以"类型"列是规范建议，属未强制。

| `type` | 必填 | 可选（参考实现会写） | 类型（未强制） |
|---|---|---|---|
| `run.start` | `agent` `argv` `cwd` `env_fingerprint` | `t` `workdir` `meta` `schema_version` | agent: str；argv: str[]；cwd: str；env_fingerprint: str；workdir: str；meta: obj |
| `model.call` | `model` `request` | `t` | model: str；request: {messages: any[], tools: any[]} |
| `model.result` | `text` `tool_calls` `usage` | `t` | text: str；tool_calls: {name: str, args: obj}[]；usage: obj |
| `tool.call` | `name` `args` | `t` | name: str；args: obj |
| `tool.result` | `name` `ok` `bytes` | `t` | name: str；ok: bool；bytes: int（输出 UTF-8 字节数） |
| `run.end` | `exit_code` `files_changed` | `t` `files` | exit_code: int；files_changed: str[]；files: {路径: sha256 或 null} |

字段来源：

- `workdir`、`files` 是实现在 DESIGN 之外补的两个字段（`docs/IMPLEMENTATION-NOTES.md`
  的"新增字段"一节）。
- `meta` 只有导入器会写：`{format, source, synthetic_timestamps, warnings}`。
- `schema_version` 目前**没有**任何实现写它（见第 11 节差异 1）。

### 4.3 语义顺序（未强制）

`run.start` 是第一条、`run.end` 是最后一条，这条**强制**（S10）。除此之外的顺序约束——
比如每个 `model.call` 后面要跟一个 `model.result`、`tool.call` 与 `tool.result` 要配对——
实现**不检查**，校验器也不判。replay 时会以"`model.result` 用尽"的形式暴露，但那是运行期
错误，不是格式错误。

---

## 5. 时间戳语义

`t` 是**相对时间**，单位秒，浮点，语义是"相对本次运行起点"。

| 情况 | 规则 |
|---|---|
| 真实录制 | `t = round(monotonic() - t0, 4)`，`t0` 是 `run.start` 之前的时刻，所以首条 `t` 接近 `0.0` 但不必等于 `0.0` |
| 导入的日志 | 每轮都有时间戳时用真实值，`t` = 本轮时间戳 − 第一轮时间戳 |
| 合成时间戳 | 只要**有一轮**缺时间戳，就把**全部** `t` 按事件序号合成：`t = index * 0.1`（`SYNTHETIC_STEP = 0.1`），并在 `run.start.meta` 里写 `synthetic_timestamps: true` 加一条明说"不是真实时间"的 `warnings` 条目 |

**真实与合成永不混用**：要么整份都是真实值，要么整份都是 `index * 0.1`。

`t` **不参与行为比较**：`events.VOLATILE_FIELDS` 把 `t` 明确列为可丢弃字段，所以两份只在
时间上不同的 cassette 行为相同。但 `t` **参与哈希**（它在 `event` 里）。

校验器只判"`t` 出现时是非负数字"（S11）；"这个数是不是真的"机器判断不了——只能靠
`meta.synthetic_timestamps` 的自我声明，所以**声明本身不可校验**（见第 10 节）。

---

## 6. 版本与前向兼容

`schema_version` 是字符串，当前值 `0.1.0`，位置在 **`run.start` 事件上**，不在记录层。
理由：记录层只有 `seq`/`prev`/`event`/`hash` 四个键且全部参与哈希，塞第五个键会让它落在
哈希保护之外；而 `event` 里的字段天然被哈希覆盖。

**缺省即 `0.1.0`**：字段不出现 = 写作 `0.1.0`。当前实现（`0.1.0`）不写这个字段，所以现存
cassette 都省略它，读出来仍然是 `0.1.0`。出现但不等于本实现认识的版本 → 非法（S9）。

前向兼容规则，分三种情形：

| 输入 | 正确处理方式 | 依据 |
|---|---|---|
| 不认识的**字段** | **忽略它**，其它照常处理 | S12；实现只取自己认识的键 |
| 不认识的**事件类型** | **拒绝整个文件**，不要跳过 | S7；`events.validate` 直接抛错 |
| 不认识的 **`schema_version`** | **拒绝**，并说明自己支持到哪个版本 | S9 |

换句话说：**开放字段、封闭类型**。加字段是 additive，不需要升版本；加事件类型、改字段
语义、改哈希算法，都必须升 `schema_version`。

---

## 7. 校验器：`tools/validate_cassette.py`

纯标准库，不 import agenttest（**第三方实现也必须能跑它**）：

```console
$ python tools/validate_cassette.py examples/good examples/bad
$ python tools/validate_cassette.py path/to/cassette.jsonl
$ python tools/validate_cassette.py --list-rules
```

逐条打印 `PASS`/`FAIL`、规则号、行号；任何 FAIL 则退出码 `1`，全通过则 `0`。

### 7.1 规则表（本规范的全部强制条目）

| 规则 | 内容 | 校验器 | 强制? |
|---|---|---|---|
| S1 | 文件是 UTF-8 JSONL，非空行都是 JSON 对象，空 cassette 非法 | 有 | 强制 |
| S2 | 记录含 `seq`/`prev`/`event`/`hash` 且基本类型正确 | 有 | 强制 |
| S3 | `seq` 从 0 起逐条 +1 | 有 | 强制 |
| S4 | `prev` 等于上一条的 `hash`，首条为 `null` | 有 | 强制 |
| S5 | `hash = sha256(canonical({seq,prev,event}))`（第 3 节） | 有 | 强制 |
| S6 | 每一行都恰好等于 `canonical(整条记录)` | 有 | 强制 |
| S7 | `type` 在白名单内 | 有 | 强制 |
| S8 | 该类型必填字段齐全（**只判存在**，不判类型） | 有 | 强制 |
| S9 | `schema_version` 缺省视为 `0.1.0`，出现则须等于 `0.1.0` | 有 | 强制 |
| S10 | 第一条事件是 `run.start`、最后一条是 `run.end` | 有 | 强制 |
| S11 | `t` 出现时是非负数字（布尔不算数字） | 有 | 强制 |
| S12 | 不认识的字段被忽略而不是报错 | 有（带未知字段仍 PASS） | 强制 |

S1 的**读取容忍范围**（BOM、CRLF、缺末尾换行、空行、行首多余 BOM）见第 1.1 节；容忍不等于放开，
非 UTF-8 编码仍然 FAIL，并且必须给出可操作建议。

### 7.2 演示：链断与缺字段各被谁抓到

两个样本都由 `examples/good/cassette.jsonl` 派生，生成方式见 `tests/test_spec_validate.py`。
第一个只改内容不改 hash（S5 抓到第 6 行），第二个删字段但重算了整条链（所以只有 S8 红、
第 5 行）——两条规则各自独立可证。

```console
$ python tools/validate_cassette.py $TEMP/at-corrupt/broken-chain.jsonl
  FAIL  S5  第 6 行的 hash 与重算值不符：记录里 '4533bd99…19'，重算 '9cad830f…72'
  结果: FAIL（1 条规则未通过：S5）

$ python tools/validate_cassette.py $TEMP/at-corrupt/missing-field.jsonl
  FAIL  S8  第 5 行的 tool.result 缺少必填字段：bytes
  结果: FAIL（1 条规则未通过：S8）
```

---

## 8. 最小示例

下面三段都是**真** cassette：由参考实现写出，且必须能通过第 7 节的全部强制规则
（`tests/test_spec_validate.py` 会逐段提取并校验，改坏一个字符测试就红）。

### 8.1 最小运行（2 条记录）

```jsonl
{"event":{"agent":"demo_agent","argv":["python","demo_agent.py"],"cwd":"/repo","env_fingerprint":"py3.12|linux","t":0.0,"type":"run.start","workdir":"."},"hash":"657f26acb5a27e6f33f0a58a4fd1742d2a62f04e5a961c4bd2740a2859bd66d1","prev":null,"seq":0}
{"event":{"exit_code":0,"files":{},"files_changed":[],"t":1.5,"type":"run.end"},"hash":"f66868e19d29002f06b1ae26dfc2272aade24c3807675b8db393b1be267de1ed","prev":"657f26acb5a27e6f33f0a58a4fd1742d2a62f04e5a961c4bd2740a2859bd66d1","seq":1}
```

### 8.2 一次工具调用，且显式写了 `schema_version`（4 条记录）

```jsonl
{"event":{"agent":"demo_agent","argv":["python","demo_agent.py"],"cwd":"/repo","env_fingerprint":"py3.12|linux","schema_version":"0.1.0","t":0.0,"type":"run.start","workdir":"."},"hash":"e39af6fd936f1ea193e66898291896d6c8b965c62de1f9c1baead2244741b112","prev":null,"seq":0}
{"event":{"args":{"path":"src/auth.py"},"name":"read_file","t":0.1,"type":"tool.call"},"hash":"af281e1e69af01624666706ac629223017d26f241c3d4cc611c4eed10787c484","prev":"e39af6fd936f1ea193e66898291896d6c8b965c62de1f9c1baead2244741b112","seq":1}
{"event":{"bytes":812,"name":"read_file","ok":true,"t":0.2,"type":"tool.result"},"hash":"61b452671b1c5e6b87448df603542005f4854777cc169ffcc9936262264003ad","prev":"af281e1e69af01624666706ac629223017d26f241c3d4cc611c4eed10787c484","seq":2}
{"event":{"exit_code":0,"files":{"src/auth.py":"9f2c000000000000000000000000000000000000000000000000000000000000"},"files_changed":["src/auth.py"],"t":0.3,"type":"run.end"},"hash":"660618fd67f8deb6f71af05b1811deb4527c34b5cea5abc809c22d43cd47071c","prev":"61b452671b1c5e6b87448df603542005f4854777cc169ffcc9936262264003ad","seq":3}
```

### 8.3 导入器写出的一份（合成时间戳 + `meta`，4 条记录）

```jsonl
{"event":{"agent":"imported:openai-chat","argv":[],"cwd":".","env_fingerprint":"imported|openai-chat","meta":{"format":"openai-chat","source":"log.jsonl","synthetic_timestamps":true,"warnings":["synthetic timestamps: t = index * 0.1s, not real time"]},"t":0.0,"type":"run.start"},"hash":"e2dfb1471c42d8debecc846c6569ba79f4d5aa634ad49f0646ccfd62fe40c1ce","prev":null,"seq":0}
{"event":{"model":"gpt-4o-mini","request":{"messages":[{"content":"why does auth fail?","role":"user"}],"tools":[]},"t":0.1,"type":"model.call"},"hash":"2cc8ae2a77220928dc582dda1a51cd660f497cc6d50f92883697f7075871d655","prev":"e2dfb1471c42d8debecc846c6569ba79f4d5aa634ad49f0646ccfd62fe40c1ce","seq":1}
{"event":{"t":0.2,"text":"Read the log first.","tool_calls":[],"type":"model.result","usage":{"in":41,"out":9}},"hash":"911f97a1b73c5bbe64492a5a783e61f7fed181c4ff8293627bb9198554394b50","prev":"2cc8ae2a77220928dc582dda1a51cd660f497cc6d50f92883697f7075871d655","seq":2}
{"event":{"exit_code":0,"files":{},"files_changed":[],"t":0.3,"type":"run.end"},"hash":"0a46104d4ce9f776587405ac91329b7caa1ada8896892598a6d577ed2db3359c","prev":"911f97a1b73c5bbe64492a5a783e61f7fed181c4ff8293627bb9198554394b50","seq":3}
```

---

## 9. 三分钟实现清单

一个新实现要"兼容"这份规范，最少做到：

1. 逐行 `json.loads`，跳过空行。
2. 维护 `prev = null`；对每条记录：比 `seq`（S3）、比 `prev`（S4）、用第 3.2 节的公式重算
   `hash`（S5）。
3. 用第 4 节的表检查事件类型与必填字段（S7、S8）。
4. 忽略不认识的字段（S12），拒绝不认识的事件类型（S7）与版本（S9）。
5. 写完一份 cassette 后跑 `python tools/validate_cassette.py <目录>`，退出码 0 才算对。

---

## 10. 未强制的事项（**机器判断不了，别假装能**）

以下条目在实现里有行为，但**不是**本规范的可校验规则，校验器不会因此判 FAIL：

| 事项 | 现实情况 |
|---|---|
| `t` 是不是"真实时间" | 只看 `run.start.meta.synthetic_timestamps` 的自我声明；声明的真假无法校验 |
| 时间戳是否单调递增 | 导入器发现乱序**只写 warning**，不重排、不报错 |
| 事件语义配对（`model.call` 与 `model.result`、`tool.call` 与 `tool.result`） | 不检查；replay 到"结果用尽"才发现 |
| `run.end.files` 里的 sha256 与真实文件是否一致 | 校验器不读工作区；只在 replay 时比对 |
| `run.start.argv` 是否真的能重放 | 导入的 cassette `argv` 是 `[]`，本来就不能 replay；格式层不判断 |
| `meta.warnings` 的内容质量 | 自由文本，无 schema |

---

## 11. 与实现的差异（以实现为准）

1. **`schema_version` 尚未被任何代码读写**（`rg schema_version src/` 只命中
   `docs/ROADMAP.md`）。本规范把它定义为"缺省 = `0.1.0`"，所以现存 cassette（`examples/good`、
   `examples/bad`、导入器产物）无需改动即合规。加写入是一次 additive 变更，不需要升版本。
2. **DESIGN 第 1 节把 `t` 画在每条事件上、把 `run.start` 写成 4 个字段**；实现额外写了
   `workdir`（run.start）与 `files`（run.end），见 `docs/IMPLEMENTATION-NOTES.md`。本规范第
   4.2 节按**实现**列字段。
3. **DESIGN 说"一行一个事件"**，措辞容易读成"一行就是事件对象"。实际每行是**记录**，事件
   在 `event` 键里。本规范按记录描述（第 2 节）。
4. **`events.validate` 只查必填字段是否存在**，不查类型；本规范把类型列标为"未强制"而不是
   假装它被强制。
