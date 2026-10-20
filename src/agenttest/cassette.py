"""cassette 读写：JSONL + sha256 哈希链（docs/DESIGN.md 第 2 节）。

一行一条记录：

    {"seq":0,"prev":null,"event":{...},"hash":"<sha256>"}

* `prev` 是上一条记录的 `hash`，任何一条被改动，链就断。
* `hash` = sha256(canonical({"seq","prev","event"}))，同时把最后一条也钉住。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from . import events as ev

CASSETTE_NAME = "cassette.jsonl"


class CassetteError(ValueError):
    """cassette 损坏、被篡改或不存在。"""


def cassette_path(target: str | Path) -> Path:
    """目录（含 cassette.jsonl）与文件两种写法都接受，按扩展名判断。"""
    p = Path(target)
    if p.name.lower().endswith(".jsonl"):
        return p
    return p / CASSETTE_NAME


def _record(seq: int, prev: str | None, event: dict) -> dict:
    body = {"seq": seq, "prev": prev, "event": event}
    return {**body, "hash": ev.digest(body)}


def write_cassette(target: str | Path, events: Iterable[dict]) -> Path:
    """把事件流写成一个带哈希链的 cassette，返回文件路径。"""
    path = cassette_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    prev: str | None = None
    for seq, event in enumerate(events):
        ev.validate(event)
        record = _record(seq, prev, event)
        lines.append(ev.canonical(record))
        prev = record["hash"]
    if not lines:
        raise CassetteError("拒绝写出空 cassette：一次运行至少要有 run.start 和 run.end")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read_cassette(target: str | Path, verify: bool = True) -> list[dict]:
    """读回事件流；默认校验哈希链。"""
    path = cassette_path(target)
    if not path.exists():
        raise CassetteError(f"找不到 cassette：{path}")
    text = path.read_text(encoding="utf-8")
    events: list[dict] = []
    prev: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise CassetteError(f"第 {lineno} 条记录不是合法 JSON：{exc}") from exc
        if not isinstance(record, dict) or "event" not in record:
            raise CassetteError(f"第 {lineno} 条记录缺少 event 字段")
        if verify:
            _verify_record(record, lineno, prev, len(events))
        events.append(record["event"])
        prev = record.get("hash")
    if not events:
        raise CassetteError(f"cassette 是空的：{path}")
    return events


def _verify_record(record: dict, lineno: int, prev: str | None, expected_seq: int) -> None:
    if record.get("seq") != expected_seq:
        raise CassetteError(
            f"第 {lineno} 条记录的 seq 应为 {expected_seq}，实际 {record.get('seq')!r}"
            "（记录被增删过）"
        )
    if record.get("prev") != prev:
        raise CassetteError(
            f"第 {lineno} 条记录的哈希链断了：prev 应为 {prev!r}，实际 {record.get('prev')!r}"
            "（前面某条记录被篡改）"
        )
    body = {"seq": record.get("seq"), "prev": record.get("prev"), "event": record.get("event")}
    expected = ev.digest(body)
    if record.get("hash") != expected:
        raise CassetteError(
            f"第 {lineno} 条记录的内容与自身 sha256 不符（记录被篡改）："
            f"记录里是 {record.get('hash')!r}，重算是 {expected!r}"
        )
    try:
        ev.validate(record["event"])
    except ev.EventError as exc:
        raise CassetteError(f"第 {lineno} 条记录：{exc}") from exc


def read_events_file(path: str | Path) -> list[dict]:
    """读 agent 子进程吐出的原始事件文件（还没有哈希链）。"""
    events: list[dict] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError as exc:
            raise CassetteError(f"事件文件第 {lineno} 行不是合法 JSON：{exc}") from exc
    return events


def chain_head(target: str | Path) -> str:
    """返回最后一条记录的哈希，方便写入交付报告。"""
    path = cassette_path(target)
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last = json.loads(line)
    if last is None:
        raise CassetteError(f"cassette 是空的：{path}")
    return last["hash"]
