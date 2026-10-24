# 「Node 的栈指向编译后的文件 / 第一帧到底是不是出错处」

> **快速答案**：V8 的栈是**倒序**的（第一帧就是抛出点），Python 的 traceback 是正序（抛出点在最后）。
> 看到 `dist/`、`build/`、`*.min.js` 说明是编译产物 —— 先开 `node --enable-source-maps`，不要改编译产物。
两个在 Node 里反复出现的误判，值得单独一页。

## 一、V8 的栈是**倒序**的：第一帧才是抛出点

真实输出（node v24.15.0，`demo.js` 第 3 行访问 `undefined.timeout`）：

```text
TypeError: Cannot read properties of undefined (reading 'timeout')
    at readConfig (C:\...\demo.js:3:14)      ← 抛出点（第一帧）
    at boot (C:\...\demo.js:7:10)             ← 调用者
    at Object.<anonymous> (C:\...\demo.js:11:3)
    at Module._compile (node:internal/modules/cjs/loader:1830:14)
    at node:internal/main/run_main_module:33:47
```

**Python 的 traceback 是正序**（最外层在前，抛出点在最末），**V8 是倒序**（抛出点在最前）。
这条差异是模型最容易搞错的地方——它常常读最后一行，然后就近改错文件。

用我们那个确定性提取器跑同一份 stderr：

```text
$ node demo.js 2>&1 | python tools/extract_frame.py
C:\...\demo.js:3  (generic, user code)
  return raw.timeout;
  stack=js/generic frames=10 user_frames=10
```

它选的是**第一个属于用户代码**的帧，并跳过 `node:internal/**`——这正是人眼看栈时该做的事。

## 二、`at file.js:` 可能是编译产物，不是你写的文件

如果栈里出现 `dist/`、`build/`、`*.min.js`、`webpack/bootstrap`、`tslib` 这类路径，说明你看的是**编译后**的位置。
两种常见来源：

| 场景 | 栈里长什么样 | 怎么回到源码 |
|---|---|---|
| TypeScript / bundler | `dist/server.js:42:9`，后面可能跟 `webpack://` 段 | 用 `--enable-source-maps`（Node 内置）或让 bundler 打开 devtool |
| 压缩后的前端产物 | `app.min.js:1:48213`（行号恒为 1） | 同样靠 source map；没有 map 就只剩这一个大行号，改不了 |

```bash
# 让 Node 自己把栈映射回 .ts / 原始源码
node --enable-source-maps dist/server.js
```

开启后栈会多出 `(file:///src/server.ts:12:7)` 这样的帧，并且**原来的编译后帧仍在**。
所以看栈时要选「第一个指向你自己源码目录」的帧，而不是第一个帧——除非编译帧就是你自己写的。

## 三、诚实的边界

`tools/extract_frame.py` **不做 source-map 重映射**，它只按路径规则挑帧。
所以在 `--enable-source-maps` 已开启的情况下，它会挑到第一个 `.ts` 帧（正确）；
而在**没有** source map 的情况下，它只能返回编译后位置——这时正确的动作是先把 source map 打开，而不是去改 `dist/` 里的文件。

## 四、最常见的三个误判

1. **改 `dist/`**：改了会被下一次 build 覆盖，而且不是你写的代码。
2. **读到 `node:internal` 就以为是项目问题**：那是 Node 自己，跳过。
3. **把 `at Object.<anonymous>` 当成函数名**：那只是模块顶层执行，说明错误发生在模块加载期，去找该文件顶层代码。