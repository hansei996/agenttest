"""文档与 CLI 不许分家：文档里写的开关必须真的存在。"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = (REPO / "src" / "agenttest" / "cli.py").read_text(encoding="utf-8")


def _doc_text():
    return (REPO / "docs" / "REGRESS.md").read_text(encoding="utf-8")


def test_every_flag_named_in_the_regress_doc_exists_in_the_cli():
    doc = _doc_text()
    flags = set(re.findall(r"--[a-z][a-z-]+", doc))
    assert "--flaky-report" in flags and "--html-views" in flags, "文档里最该讲的两个开关没了？"
    missing = sorted(flag for flag in flags if (chr(34) + flag + chr(34)) not in CLI)
    assert missing == [], "文档提到了但 CLI 里没有的开关：" + ", ".join(missing)


def test_regress_doc_states_the_three_noise_rules():
    doc = _doc_text()
    assert "只有 `MIXED_OBSERVED` 算噪声" in doc
    assert "INSUFFICIENT_RUNS" in doc
    assert "不给 `--flaky-report` 时行为一字不变" in doc


def test_readme_command_table_mentions_the_new_flags():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "--flaky-report" in readme
    assert "--html-views" in readme
    assert "plan" in readme
