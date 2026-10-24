"""export：JUnit / SARIF 导出的回归测试。"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from agenttest.export import ExportError, to_junit, to_sarif


def _report(ok_first=True):
    return {
        "version": "1",
        "generated_at": "2026-10-24T00:00:00Z",
        "runs": [
            {
                "run_id": "bad",
                "path": "examples/bad/cassette.jsonl",
                "duration": 0.015,
                "assertions": [
                    {"expr": "before:quote_error", "ok": ok_first, "message": "FAIL before:quote_error — 第 4 个事件"},
                ],
                "failures": [{"expr": "before:quote_error", "event_index": 4, "message": "x"}],
            }
        ],
    }


def test_junit_is_parseable_and_counts_match():
    xml = to_junit(_report(ok_first=False))
    root = ET.fromstring(xml)
    assert root.tag == "testsuites"
    assert root.get("tests") == "1"
    assert root.get("failures") == "1"
    case = root.find("./testsuite/testcase")
    assert case.get("name") == "before:quote_error"
    assert case.find("failure") is not None


def test_junit_has_no_failure_when_passing():
    root = ET.fromstring(to_junit(_report(ok_first=True)))
    assert root.get("failures") == "0"
    assert root.find("./testsuite/testcase/failure") is None


def test_sarif_is_valid_shape():
    sarif = json.loads(to_sarif(_report(ok_first=False)))
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "agenttest"
    assert len(run["results"]) == 1
    result = run["results"][0]
    assert result["ruleId"] == "before:quote_error"
    assert result["level"] == "error"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 5


def test_sarif_has_no_results_when_passing():
    sarif = json.loads(to_sarif(_report(ok_first=True)))
    assert sarif["runs"][0]["results"] == []


def test_bad_format_and_bad_report_are_loud(tmp_path):
    from agenttest.export import export

    report = tmp_path / "r.json"
    report.write_text(json.dumps(_report()), encoding="utf-8")
    with pytest.raises(ExportError):
        export(report, "html")
    with pytest.raises(ExportError):
        export(tmp_path / "missing.json", "junit")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ExportError):
        export(broken, "junit")