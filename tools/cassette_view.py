#!/usr/bin/env python3
"""cassette_view —— 把一个 cassette 变成单文件离线 HTML，双击就能看。

设计取舍（都是为了避免「打开就卡死」和「看起来对但其实不完整」）：
  * 零外部依赖：只用标准库，生成的 HTML 不引用任何 CDN；
  * 不一次性渲染全部事件：DOM 只铺前 500 行，滚动/搜索时按需追加；
  * 软上限：>30000 条事件或 >24MB 时截断，并在页面上**明确写出截断了**；
  * 硬上限：>500MB 直接拒绝（那时它已经不是「一眼能看」的东西了）；
  * 哈希链当场重算：断了就把**第一个断点的行号**放在最上面，而不是装作没事；
  * run.start.meta.unobserved 必须显示 —— 「哪些事件没观测到」和事件本身一样重要。

用法：
    python tools/cassette_view.py examples/good
    python tools/cassette_view.py runs/latest/cassette.jsonl --out /tmp/view.html
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from html import escape
from pathlib import Path

SOFT_EVENT_CAP = 30_000
SOFT_BYTE_CAP = 24 * 1024 * 1024
HARD_BYTE_CAP = 500 * 1024 * 1024
WINDOW = 500
CASSETTE_NAME = "cassette.jsonl"


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def resolve(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        p = p / CASSETTE_NAME
    if not p.exists():
        raise SystemExit("找不到 cassette：" + str(p))
    return p


def load(path: Path):
    size = path.stat().st_size
    if size > HARD_BYTE_CAP:
        raise SystemExit(
            "这个文件 %.1f MB，超过硬上限 %.0f MB —— 用 jq/grep 先切片，别指望一屏看完"
            % (size / 1024 / 1024, HARD_BYTE_CAP / 1024 / 1024)
        )
    truncated_for_bytes = size > SOFT_BYTE_CAP
    records = []
    prev = None
    first_break = None
    with path.open("r", encoding="utf-8-sig") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                if first_break is None:
                    first_break = {"line": lineno, "why": "这一行不是合法 JSON"}
                break
            body = {"seq": record.get("seq"), "prev": record.get("prev"), "event": record.get("event")}
            digest = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
            if digest != record.get("hash") and first_break is None:
                first_break = {"line": lineno, "why": "哈希对不上（内容被改过，或者不是这个格式）"}
            records.append(record)
            prev = record.get("hash")
            if len(records) >= SOFT_EVENT_CAP:
                truncated_for_bytes = True
                break
    return {
        "records": records,
        "size": size,
        "truncated": truncated_for_bytes,
        "first_break": first_break,
        "path": path,
    }


def summarize(event: dict) -> str:
    etype = event.get("type", "?")
    if etype == "run.start":
        return "agent=" + str(event.get("agent")) + " argv=" + " ".join(map(str, event.get("argv") or []))
    if etype == "run.end":
        changed = event.get("files_changed") or []
        return "exit=%s files_changed=%d" % (event.get("exit_code"), len(changed))
    if etype == "model.call":
        request = event.get("request") or {}
        messages = request.get("messages") or []
        return "model=%s messages=%d tools=%d" % (
            event.get("model"),
            len(messages),
            len(request.get("tools") or []),
        )
    if etype == "model.result":
        text = str(event.get("text") or "")
        calls = event.get("tool_calls") or []
        preview = text.replace("\n", " ")[:80]
        return "text=" + preview + (" tool_calls=" + str(len(calls)) if calls else "")
    if etype == "tool.call":
        return "name=" + str(event.get("name")) + " args=" + canonical(event.get("args") or {})[:80]
    if etype == "tool.result":
        return "name=%s ok=%s bytes=%s" % (event.get("name"), event.get("ok"), event.get("bytes"))
    return canonical(event)[:100]


def render(data: dict, title: str) -> str:
    records = data["records"]
    first = records[0]["event"] if records else {}
    meta = first.get("meta")
    unobserved = (meta or {}).get("unobserved")
    if meta is None:
        unobserved = None

    rows = []
    for record in records:
        event = record.get("event") or {}
        hay = (str(record.get("seq")) + " " + str(event.get("type")) + " " + summarize(event)).lower()
        rows.append(
            "<tr data-hay='" + escape(hay, quote=True) + "'>"
            + "<td class=num>" + escape(str(record.get("seq"))) + "</td>"
            + "<td class=num>" + escape(str(event.get("t", ""))) + "</td>"
            + "<td><span class=ty>" + escape(str(event.get("type"))) + "</span></td>"
            + "<td>" + escape(summarize(event)) + "</td></tr>"
        )

    if data["first_break"]:
        verdict_class = "bad"
        verdict = (
            "哈希链断了：第 %s 行 —— %s"
            % (data["first_break"]["line"], data["first_break"]["why"])
        )
    else:
        verdict_class = "ok"
        verdict = "哈希链完好：%d 条记录逐一重算通过" % len(records)

    notes = []
    if data["truncated"]:
        notes.append(
            "已截断：只渲染前 %d 条（文件 %.1f MB）。要全看请用 grep/jq 切片。"
            % (len(records), data["size"] / 1024 / 1024)
        )
    if unobserved is None:
        notes.append("未被观测到的记录：这份 cassette 没有写 meta.unobserved —— 意思是「没记」，不是「都观测到了」")
    elif unobserved:
        notes.append("未观测事件：" + "、".join(str(x) for x in unobserved))
    else:
        notes.append("未观测事件：无（录制时六类事件都看到了）")

    head_meta = "agent=%s · argv=%s · %d 条记录 · 文件 %.1f KB" % (
        first.get("agent"),
        " ".join(map(str, first.get("argv") or [])),
        len(records),
        data["size"] / 1024,
    )

    css = (
        "body{font:14px/1.5 -apple-system,Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1b1b1b}"
        "h1{font-size:18px;margin:0 0 4px}"
        ".meta{color:#666;margin:0 0 12px}"
        ".verdict{padding:10px 12px;border-radius:6px;margin:0 0 10px;font-weight:600}"
        ".verdict.ok{background:#e8f5e9;color:#1b5e20}"
        ".verdict.bad{background:#ffebee;color:#b71c1c}"
        ".note{background:#fff8e1;color:#5d4037;padding:8px 12px;border-radius:6px;margin:0 0 12px}"
        "input{width:340px;padding:6px 8px;border:1px solid #ccc;border-radius:6px;margin:0 0 12px}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border-bottom:1px solid #eee;padding:6px 8px;vertical-align:top;text-align:left}"
        "th{background:#fafafa;position:sticky;top:0}"
        "td.num{text-align:right;color:#888;width:70px;font-variant-numeric:tabular-nums}"
        ".ty{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:#f1f3f4;padding:1px 6px;border-radius:4px}"
        "#more{margin:12px 0;color:#666}"
    )
    # 注意：JS 里不用模板字符串，避免和生成器本身的引号纠缠
    js = (
        "var rows=[].slice.call(document.querySelectorAll('tr[data-hay]'));"
        "var shown=" + str(WINDOW) + ";"
        "var more=document.getElementById('more');"
        "function paint(){"
        "var q=document.getElementById('q').value.trim().toLowerCase();"
        "var hits=rows.filter(function(r){return !q||r.getAttribute('data-hay').indexOf(q)>=0;});"
        "rows.forEach(function(r){r.style.display='none';});"
        "hits.slice(0,shown).forEach(function(r){r.style.display='';});"
        "more.textContent=hits.length>shown?('显示 '+shown+' / 命中 '+hits.length+'，滚动到底会自动加载'):('命中 '+hits.length+' 条');"
        "}"
        "document.getElementById('q').addEventListener('input',function(){shown=" + str(WINDOW) + ";paint();});"
        "window.addEventListener('scroll',function(){"
        "if(window.innerHeight+window.scrollY>=document.body.offsetHeight-200){shown+=" + str(WINDOW) + ";paint();}});"
        "paint();"
    )

    return (
        "<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        "<title>" + escape(title) + "</title><style>" + css + "</style></head><body>"
        "<h1>" + escape(title) + "</h1>"
        "<p class=meta>" + escape(head_meta) + "</p>"
        "<div class='verdict " + verdict_class + "'>" + escape(verdict) + "</div>"
        + "".join("<div class=note>" + escape(n) + "</div>" for n in notes)
        + "<input id=q placeholder='搜事件类型 / 工具名 / 参数 / 文本…'>"
        + "<div id=more></div>"
        + "<table><thead><tr><th>seq</th><th>t</th><th>type</th><th>摘要</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + "<script>" + js + "</script>"
        + "</body></html>"
    )


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="把一个 cassette 变成单文件离线 HTML")
    parser.add_argument("path", help="cassette 目录或 cassette.jsonl")
    parser.add_argument("--out", dest="out", default=None, help="输出 HTML 路径")
    args = parser.parse_args(argv)

    path = resolve(args.path)
    data = load(path)
    title = "cassette · " + str(data["records"][0]["event"].get("agent") if data["records"] else path.name)
    html = render(data, title)

    out = Path(args.out) if args.out else path.parent / "view.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("已生成 " + str(out) + "（" + str(len(data["records"])) + " 条记录，" + str(len(html)) + " 字节）")
    if data["first_break"]:
        print("警告：哈希链在第 " + str(data["first_break"]["line"]) + " 行断了 —— " + data["first_break"]["why"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))