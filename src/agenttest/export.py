"""把 regress 的报告导出成别的工具已经认识的样子。

为什么要它：JUnit XML 是 CI 看板的通用语言，SARIF 是代码扫描的通用语言。
cassette 是无损原件，这两个是交换件 —— 别人不用装我们也能在我们的结果上看到红绿。
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

FORMATS = ("junit", "sarif")


class ExportError(ValueError):
    """报告读不了或格式不支持。"""


def load_report(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise ExportError("报告不存在：" + str(p))
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise ExportError("报告不是合法 JSON：" + str(exc)) from exc
    if not isinstance(data, dict) or "runs" not in data:
        raise ExportError("这不是 agenttest regress 的报告：缺 runs 字段")
    return data


def _cases(report: dict):
    for run in report.get("runs", []):
        run_id = str(run.get("run_id") or run.get("path") or "run")
        for item in run.get("assertions", []):
            yield run_id, item, run


def to_junit(report: dict) -> str:
    cases = list(_cases(report))
    failures = sum(1 for _, item, _ in cases if not item.get("ok"))
    out = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append(
        '<testsuites name="agenttest" tests="%d" failures="%d">' % (len(cases), failures)
    )
    for run in report.get("runs", []):
        run_id = str(run.get("run_id") or run.get("path") or "run")
        items = run.get("assertions", [])
        bad = sum(1 for item in items if not item.get("ok"))
        out.append(
            '  <testsuite name=%s tests="%d" failures="%d" time="%.3f">'
            % (quoteattr(run_id), len(items), bad, float(run.get("duration") or 0.0))
        )
        for item in items:
            expr = str(item.get("expr") or "assert")
            out.append('    <testcase classname=%s name=%s time="0">' % (quoteattr("agenttest." + run_id), quoteattr(expr)))
            if not item.get("ok"):
                message = str(item.get("message") or "assertion failed")
                out.append("      <failure message=%s>%s</failure>" % (quoteattr(message), escape(message)))
            out.append("    </testcase>")
        out.append("  </testsuite>")
    out.append("</testsuites>")
    return chr(10).join(out) + chr(10)


def to_sarif(report: dict) -> str:
    rules = {}
    results = []
    for run_id, item, run in _cases(report):
        expr = str(item.get("expr") or "assert")
        rules.setdefault(expr, {"id": expr, "shortDescription": {"text": "agenttest assertion: " + expr}})
        if item.get("ok"):
            continue
        index = None
        for failure in run.get("failures", []):
            if failure.get("expr") == expr and failure.get("event_index") is not None:
                index = int(failure["event_index"])
                break
        location = {
            "physicalLocation": {
                "artifactLocation": {"uri": str(run.get("path") or run_id).replace("\\", "/")},
            }
        }
        if index is not None:
            location["physicalLocation"]["region"] = {"startLine": max(1, index + 1)}
        results.append({
            "ruleId": expr,
            "level": "error",
            "message": {"text": str(item.get("message") or "assertion failed")},
            "locations": [location],
        })
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "agenttest",
                        "informationUri": "https://github.com/hansei996/agenttest",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, ensure_ascii=False, indent=2) + chr(10)


def export(report_path: str | Path, fmt: str, out_path: str | Path | None = None) -> str:
    if fmt not in FORMATS:
        raise ExportError("不支持的格式：" + fmt + "（可选：" + ", ".join(FORMATS) + "）")
    report = load_report(report_path)
    text = to_junit(report) if fmt == "junit" else to_sarif(report)
    if out_path:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return text
