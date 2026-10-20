#!/usr/bin/env python3
"""reference_reader：第三方视角的 cassette 读取实现（只依赖标准库）。

这个文件故意**不 import agenttest，也不 import tools/validate_cassette.py**。
它只照着 docs/CASSETTE-SPEC.md 写：读懂格式、独立校验哈希链与必填字段、读出事件。
它是 ROADMAP v1.0「至少一个第三方实现能读写同一份 cassette」的活证据——如果这份
规范只能被作者自己的代码读懂，那就不叫规范。

    python tools/reference_reader.py examples/good/cassette.jsonl
    python tools/reference_reader.py examples/good          # 目录也接受

成功：打印事件计数与链头，exit 0。失败：打印第几行、哪条规则，exit 1。
"""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

# 规范第 4.2 节：每类事件必须出现的字段。
REQUIRED = {
    "run.start": ("agent", "argv", "cwd", "env_fingerprint"),
    "model.call": ("model", "request"),
    "model.result": ("text", "tool_calls", "usage"),
    "tool.call": ("name", "args"),
    "tool.result": ("name", "ok", "bytes"),
    "run.end": ("exit_code", "files_changed"),
}


class Bad(Exception):
    """cassette 不符合规范。"""


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def canonical(obj) -> str:
    """规范 3.1：键排序、紧凑分隔符、非 ASCII 不转义。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(obj) -> str:
    """规范 3.2：sha256(canonical(body) 的 UTF-8 字节)，小写十六进制。"""
    return sha256(canonical(obj).encode("utf-8")).hexdigest()


def read_cassette(path: Path):
    if path.is_dir():
        path = path / "cassette.jsonl"
    if not path.is_file():
        raise Bad("找不到 cassette：" + str(path))
    prev, head, counts, total = None, None, {}, 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise Bad(f"第 {lineno} 行不是合法 JSON：{exc}") from exc
        for key in ("seq", "prev", "event", "hash"):
            if key not in record:
                raise Bad(f"第 {lineno} 行缺少 {key} 字段")
        if record["seq"] != total:
            raise Bad(f"第 {lineno} 行的 seq 应为 {total}，实际 {record['seq']!r}")
        if record["prev"] != prev:
            raise Bad(f"第 {lineno} 行的哈希链断了：prev 应为 {prev!r}，实际 {record['prev']!r}")
        body = {"seq": record["seq"], "prev": record["prev"], "event": record["event"]}
        if digest(body) != record["hash"]:
            raise Bad(f"第 {lineno} 行的 hash 与重算值不符（内容被改过）")
        event, etype = record["event"], record["event"].get("type")
        if etype not in REQUIRED:
            raise Bad(f"第 {lineno} 行的事件类型 {etype!r} 不在 6 类白名单内")
        missing = [name for name in REQUIRED[etype] if name not in event]
        if missing:
            raise Bad(f"第 {lineno} 行的 {etype} 缺少必填字段：{','.join(missing)}")
        counts[etype] = counts.get(etype, 0) + 1
        head, prev, total = record["hash"], record["hash"], total + 1
    if not total:
        raise Bad("cassette 是空的")
    return counts, head, total


def main(argv=None) -> int:
    _force_utf8()
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        print("用法: python tools/reference_reader.py <cassette.jsonl|目录>", file=sys.stderr)
        return 2
    try:
        counts, head, total = read_cassette(Path(argv[1]))
    except Bad as exc:
        print("FAIL " + str(exc))
        return 1
    print(f"OK {total} 条记录")
    for etype in REQUIRED:
        if etype in counts:
            print(f"  {etype} {counts[etype]}")
    print("chain head: " + head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
