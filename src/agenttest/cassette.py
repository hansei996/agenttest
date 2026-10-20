"""cassette 读写：JSONL + sha256 哈希链（docs/DESIGN.md 第 2 节）。

一行一条记录：

    {"seq":0,"prev":null,"event":{...},"hash":"<sha256>"}

* `prev` 是上一条记录的 `hash`，任何一条被改动，链就断。
* `hash` = sha256(canonical({"seq","prev","event"}))，同时把最后一条也钉住。

编码约定：**写出去一定是 UTF-8 无 BOM**；读进来容忍 UTF-8 BOM
（Windows 记事本 / `Set-Content -Encoding utf8` 会加），其它编码则给出可操作的报错。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from . import events as ev

CASSETTE_NAME = "cassette.jsonl"
UTF8_BOM = b"\xef\xbb\xbf"

# 只认 UTF-8；这些 BOM 说明文件是别的编码存的，直接说清楚比抛 JSON 错有用。
_OTHER_BOMS = (
    (b"\x00\x00\xfe\xff", "UTF-32 BE"),
    (b"\xff\xfe\x00\x00", "UTF-32 LE"),
    (b"\xfe\xff", "UTF-16 BE"),
    (b"\xff\xfe", "UTF-16 LE"),
)


class CassetteError(ValueError):
    """cassette 损坏、被篡改、编码不对或不存在。"""


def cassette_path(target: str | Path) -> Path:
    """目录（含 cassette.jsonl）与文件两种写法都接受，按扩展名判断。"""
    p = Path(target)
    if p.name.lower().endswith(".jsonl"):
        return p
    return p / CASSETTE_NAME


def _record(seq: int, prev: str | None, event: dict) -> dict:
    body = {"seq": seq, "prev": prev, "event": event}
    return {**body, "hash": ev.digest(body)}


def _hex_preview(raw: bytes, limit: int = 8) -> str:
    return " ".join(f"{byte:02X}" for byte in raw[:limit])


def _read_text(path: Path, kind: str = "cassette") -> str:
    """按 UTF-8 读文本，吃掉可选的 UTF-8 BOM，别的情况给出能照做的提示。"""
    raw = path.read_bytes()
    body = raw[len(UTF8_BOM):] if raw.startswith(UTF8_BOM) else raw
    if not body.strip():
        raise CassetteError(f"{kind}是空的：{path}")
    for bom, name in _OTHER_BOMS:
        if raw.startswith(bom):
            raise CassetteError(
                f"{kind}是 {name} 编码（带 BOM），不是 UTF-8：{path}。"
                "agenttest 只读 UTF-8（有没有 BOM 都行），请转码后重试，"
                "例如 PowerShell：Get-Content -Raw '<file>' | Set-Content -Encoding utf8 '<file>'；"
                "或 iconv -f UTF-16 -t UTF-8 in.jsonl > out.jsonl"
            )
    if b"\x00" in body:
        raise CassetteError(
            f"{kind}看起来是二进制文件而不是 JSONL 文本：{path}"
            f"（文件开头 {_hex_preview(raw)}，里面有 NUL 字节）。"
            "cassette 必须是一行一个 JSON 的 UTF-8 文本：确认路径没指错，"
            "或者用 agenttest record 重新录一份"
        )
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        lineno = body[: exc.start].count(b"\n") + 1
        raise CassetteError(
            f"{kind}不是合法的 UTF-8 文本：{path}"
            f"（文件开头 {_hex_preview(raw)}，第 {lineno} 行第 {exc.start} 字节解不开：{exc.reason}）。"
            "常见原因是文件被别的编码（GBK、UTF-16 无 BOM 等）存过，"
            "或者里面混了非文本内容；请另存为 UTF-8 后重试"
        ) from exc


def _json_line_error(label: str, line: str, exc: ValueError) -> CassetteError:
    return CassetteError(
        f"{label}不是合法 JSON（文件本身已按 UTF-8 解码成功，所以不是编码问题）：{exc}。"
        f"这一行开头是 {line.strip()[:60]!r}；JSONL 要求一行一个完整 JSON 对象，"
        "空行会被跳过，但字符串里不能有裸换行"
    )


def write_cassette(target: str | Path, events: Iterable[dict]) -> Path:
    """把事件流写成一个带哈希链的 cassette，返回文件路径。

    写出去一定是 UTF-8 无 BOM、LF 换行（跨平台产物字节一致）。
    """
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
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def read_cassette(target: str | Path, verify: bool = True) -> list[dict]:
    """读回事件流；默认校验哈希链。文件带 UTF-8 BOM 也能读。"""
    path = cassette_path(target)
    if not path.exists():
        raise CassetteError(f"找不到 cassette：{path}")
    text = _read_text(path, kind="cassette ")
    events: list[dict] = []
    prev: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise _json_line_error(f"第 {lineno} 条记录", line, exc) from exc
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
    lines = _read_text(Path(path), kind="事件文件 ").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError as exc:
            raise _json_line_error(f"事件文件第 {lineno} 行", line, exc) from exc
    return events


def chain_head(target: str | Path) -> str:
    """返回最后一条记录的哈希，方便写入交付报告。"""
    path = cassette_path(target)
    last = None
    for line in _read_text(path, kind="cassette ").splitlines():
        if line.strip():
            last = json.loads(line)
    if last is None:
        raise CassetteError(f"cassette 是空的：{path}")
    return last["hash"]
