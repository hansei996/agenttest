#!/usr/bin/env python3
"""validate_cassette：独立的 cassette 校验器（只依赖标准库）。

它实现 docs/CASSETTE-SPEC.md 里所有"能被机器判定"的规则，逐条给出 PASS / FAIL
与行号。任何 FAIL 都让进程以 1 退出，所以可以直接放进 CI：

    python tools/validate_cassette.py examples/good examples/bad
    python tools/validate_cassette.py path/to/cassette.jsonl

它不 import agenttest：一个"别人写的"实现也必须能跑它。所以事件白名单与必填字段
在这里硬编码，再由 tests/test_spec_validate.py 对着 src/agenttest/events.py 做
逐字一致性检查——任一侧漂移，测试就红。

规则编号与 docs/CASSETTE-SPEC.md 的表格一一对应。规范里标了「未强制」的条目不在
本工具的判定范围内；用 --list-rules 看本工具认哪 12 条。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "0.1.0"
CASSETTE_NAME = "cassette.jsonl"

# 与 src/agenttest/events.py 的 EVENT_TYPES / REQUIRED_FIELDS 逐字一致。
EVENT_TYPES = (
    "run.start",
    "model.call",
    "model.result",
    "tool.call",
    "tool.result",
    "run.end",
)

REQUIRED_FIELDS = {
    "run.start": ("agent", "argv", "cwd", "env_fingerprint"),
    "model.call": ("model", "request"),
    "model.result": ("text", "tool_calls", "usage"),
    "tool.call": ("name", "args"),
    "tool.result": ("name", "ok", "bytes"),
    "run.end": ("exit_code", "files_changed"),
}

RECORD_KEYS = ("seq", "prev", "event", "hash")

KNOWN_EVENT_FIELDS = {
    "type", "t", "agent", "argv", "cwd", "env_fingerprint", "workdir", "meta",
    "schema_version", "model", "request", "text", "tool_calls", "usage",
    "name", "args", "ok", "bytes", "exit_code", "files_changed", "files",
}

RULES = (
    ("S1", "文件是 UTF-8 JSONL：非空行必须是 JSON 对象，空行忽略"),
    ("S2", "记录形状：seq / prev / event / hash 四个键齐全且类型正确"),
    ("S3", "seq 从 0 起逐条 +1（记录没有被增删）"),
    ("S4", "prev 等于上一条记录的 hash，首条为 null（哈希链）"),
    ("S5", "hash = sha256(canonical({seq,prev,event}))（内容没有被篡改）"),
    ("S6", "每一行都是规范化 JSON：键排序、紧凑分隔符、无多余空白"),
    ("S7", "事件类型在 6 类白名单内"),
    ("S8", "事件携带该类型的全部必填字段"),
    ("S9", "run.start.schema_version 缺省视为 0.1.0；出现则必须是 0.1.0"),
    ("S10", "第一条事件是 run.start，最后一条是 run.end"),
    ("S11", "t 出现时是非负数字（布尔不算数字）"),
    ("S12", "记录里不认识的字段一律忽略，不报错（前向兼容）"),
)


class Finding:
    __slots__ = ("ok", "rule", "message")

    def __init__(self, ok: bool, rule: str, message: str) -> None:
        self.ok = ok
        self.rule = rule
        self.message = message


def canonical(obj) -> str:
    """规范化的单行 JSON 文本：键排序、紧凑分隔符、不转义非 ASCII。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(obj) -> str:
    """被哈希的字节 = canonical(obj) 的 UTF-8 编码；摘要用 sha256 的小写十六进制。"""
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def cassette_path(target: Path) -> Path:
    if target.name.lower().endswith(".jsonl"):
        return target
    return target / CASSETTE_NAME


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _sorted(findings) -> list:
    order = [rule for rule, _title in RULES]
    return sorted(findings, key=lambda f: order.index(f.rule))


def validate_text(text: str) -> list:
    """校验一份 JSONL 文本，返回 Finding 列表（PASS / FAIL 混排）。"""
    findings = []
    raw_lines = text.splitlines()
    numbered = [(i + 1, line) for i, line in enumerate(raw_lines) if line.strip()]

    # S1：能否逐行解析成 JSON 对象
    records = []
    bad_json = []
    bad_obj = []
    for lineno, line in numbered:
        try:
            value = json.loads(line)
        except ValueError as exc:
            bad_json.append((lineno, str(exc)))
            continue
        if not isinstance(value, dict):
            bad_obj.append((lineno, type(value).__name__))
            continue
        records.append((lineno, line, value))
    if bad_json or bad_obj:
        detail = "; ".join(
            ["第 %d 行不是合法 JSON（%s）" % (n, e) for n, e in bad_json]
            + ["第 %d 行不是 JSON 对象而是 %s" % (n, t) for n, t in bad_obj]
        )
        findings.append(Finding(False, "S1", detail))
    elif not records:
        findings.append(Finding(False, "S1", "文件里没有任何记录（空 cassette 不合法）"))
    else:
        findings.append(
            Finding(True, "S1", "%d 条记录都是 JSON 对象（忽略空行 %d 个）"
                    % (len(records), len(raw_lines) - len(numbered)))
        )

    # S2：记录形状
    shaped = []
    problems = []
    for lineno, line, record in records:
        missing = [key for key in RECORD_KEYS if key not in record]
        if missing:
            problems.append("第 %d 行缺少 %s" % (lineno, ", ".join(missing)))
            continue
        if not isinstance(record["seq"], int) or isinstance(record["seq"], bool):
            problems.append("第 %d 行的 seq 不是整数" % lineno)
            continue
        if record["prev"] is not None and not isinstance(record["prev"], str):
            problems.append("第 %d 行的 prev 既不是字符串也不是 null" % lineno)
            continue
        if not isinstance(record["event"], dict):
            problems.append("第 %d 行的 event 不是对象" % lineno)
            continue
        if not isinstance(record["hash"], str):
            problems.append("第 %d 行的 hash 不是字符串" % lineno)
            continue
        shaped.append((lineno, line, record))
    findings.append(
        Finding(not problems, "S2",
                "; ".join(problems) if problems
                else "%d 条记录形状正确（多余的键按 S12 忽略）" % len(shaped))
    )

    # S3 / S4 / S5 / S6
    seq_bad = []
    prev_bad = []
    hash_bad = []
    canon_bad = []
    expected_prev = None
    for index, (lineno, line, record) in enumerate(shaped):
        if record["seq"] != index:
            seq_bad.append("第 %d 行的 seq 应为 %d，实际 %r" % (lineno, index, record["seq"]))
        if record["prev"] != expected_prev:
            prev_bad.append("第 %d 行的 prev 应为 %r，实际 %r"
                            % (lineno, expected_prev, record["prev"]))
        body = {"seq": record["seq"], "prev": record["prev"], "event": record["event"]}
        expected = digest(body)
        if record["hash"] != expected:
            hash_bad.append("第 %d 行的 hash 与重算值不符：记录里 %r，重算 %r"
                            % (lineno, record["hash"], expected))
        if line != canonical(record):
            canon_bad.append("第 %d 行不是规范化 JSON（键未排序或有空白差异）" % lineno)
        expected_prev = record["hash"]
    findings.append(Finding(not seq_bad, "S3", "; ".join(seq_bad) if seq_bad else "seq 连续"))
    findings.append(Finding(not prev_bad, "S4",
                            "; ".join(prev_bad) if prev_bad else "哈希链完整"))
    findings.append(Finding(not hash_bad, "S5", "; ".join(hash_bad) if hash_bad
                            else "每条记录的内容与自身 sha256 相符"))
    findings.append(Finding(not canon_bad, "S6", "; ".join(canon_bad) if canon_bad
                            else "每行都是规范化 JSON"))

    # S7 / S8 / S9 / S11：逐事件
    type_bad = []
    field_bad = []
    version_bad = []
    time_bad = []
    events = []
    for lineno, line, record in shaped:
        event = record["event"]
        etype = event.get("type")
        events.append((lineno, event))
        if etype not in EVENT_TYPES:
            type_bad.append("第 %d 行的事件类型 %r 不在白名单内" % (lineno, etype))
            continue
        missing = [name for name in REQUIRED_FIELDS[etype] if name not in event]
        if missing:
            field_bad.append("第 %d 行的 %s 缺少必填字段：%s"
                             % (lineno, etype, ", ".join(missing)))
        if etype == "run.start" and "schema_version" in event:
            if event["schema_version"] != SCHEMA_VERSION:
                version_bad.append("第 %d 行的 schema_version 是 %r，本工具只认识 %r"
                                   % (lineno, event["schema_version"], SCHEMA_VERSION))
        if "t" in event and not (_is_number(event["t"]) and event["t"] >= 0):
            time_bad.append("第 %d 行的 t 不是非负数字：%r" % (lineno, event["t"]))

    findings.append(Finding(not type_bad, "S7", "; ".join(type_bad) if type_bad
                            else "事件类型都在白名单内"))
    findings.append(Finding(not field_bad, "S8", "; ".join(field_bad) if field_bad
                            else "必填字段齐全"))
    findings.append(Finding(not version_bad, "S9", "; ".join(version_bad) if version_bad
                            else "schema_version 缺省或等于 %s" % SCHEMA_VERSION))
    findings.append(Finding(not time_bad, "S11", "; ".join(time_bad) if time_bad
                            else "t 都是非负数字"))

    # S10：首尾
    if events:
        first_line, first = events[0]
        last_line, last = events[-1]
        problems = []
        if first.get("type") != "run.start":
            problems.append("第 %d 行是第一条事件，但不是 run.start（是 %r）"
                            % (first_line, first.get("type")))
        if last.get("type") != "run.end":
            problems.append("第 %d 行是最后一条事件，但不是 run.end（是 %r）"
                            % (last_line, last.get("type")))
        findings.append(Finding(not problems, "S10", "; ".join(problems) if problems
                                else "起点是 run.start，收尾是 run.end"))
    else:
        findings.append(Finding(False, "S10", "没有可判断的事件"))

    # S12：未知字段只被忽略，不产生 FAIL；这条只报告观察到几个。
    unknown = sorted({
        key
        for _lineno, event in events
        for key in event
        if key not in KNOWN_EVENT_FIELDS
    })
    findings.append(Finding(True, "S12", "忽略 %d 个未知字段%s"
                            % (len(unknown), ("：" + ", ".join(unknown)) if unknown else "")))
    return _sorted(findings)


def validate_path(target: Path) -> list:
    path = cassette_path(target)
    if not path.is_file():
        return [Finding(False, "S1", "找不到 cassette：%s" % path)]
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [Finding(False, "S1", "不是合法的 UTF-8：%s" % exc)]
    return validate_text(text)


def report(targets) -> int:
    failed = 0
    for target in targets:
        path = cassette_path(target)
        print("cassette: %s" % path)
        findings = validate_path(target)
        for finding in findings:
            print("  %s  %s  %s"
                  % ("PASS" if finding.ok else "FAIL", finding.rule, finding.message))
        bad = [f for f in findings if not f.ok]
        if bad:
            failed += 1
            print("  结果: FAIL（%d 条规则未通过：%s）"
                  % (len(bad), ", ".join(f.rule for f in bad)))
        else:
            print("  结果: PASS（%d 条规则全部通过）" % len(findings))
        print("")
    if failed:
        print("FAIL: %d/%d 个 cassette 未通过校验" % (failed, len(targets)))
        return 1
    print("PASS: %d/%d 个 cassette 通过校验" % (len(targets), len(targets)))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_cassette.py",
        description="校验 agenttest cassette（JSONL + sha256 哈希链），只依赖标准库。",
    )
    parser.add_argument("targets", nargs="*", metavar="PATH",
                        help="cassette.jsonl 或其所在目录；可以给多个")
    parser.add_argument("--list-rules", action="store_true",
                        help="打印规则编号与含义后退出")
    args = parser.parse_args(argv)

    if args.list_rules:
        for rule, title in RULES:
            print("%s  %s" % (rule, title))
        return 0
    if not args.targets:
        parser.print_usage(sys.stderr)
        print("error: 至少给一个 cassette 路径", file=sys.stderr)
        return 2
    return report([Path(item) for item in args.targets])


if __name__ == "__main__":
    raise SystemExit(main())
