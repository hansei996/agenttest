"""六种断言语法：文档里写了就要真能跑（逐个在真实 cassette 上验证）。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from agenttest.assertions import evaluate
from agenttest.cassette import read_cassette

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def good():
    return read_cassette(REPO / "examples" / "good" / "cassette.jsonl")


@pytest.fixture(scope="module")
def bad():
    return read_cassette(REPO / "examples" / "bad" / "cassette.jsonl")


@pytest.mark.parametrize("expr", [
    "before:quote_error",
    "tool:read_file",
    "never:tool=delete_file",
    "touched:src/auth.py",
    "exit:0",
])
def test_form_passes_on_the_well_behaved_run(good, expr):
    result = evaluate(expr, good)
    assert result.ok, expr + " 在 examples/good 上应当通过：" + result.message


@pytest.mark.parametrize("expr", [
    "before:quote_error",
    "never:tool=edit_file",
    "touched:logs/app.log",
])
def test_form_fails_on_the_lazy_run(bad, expr):
    result = evaluate(expr, bad)
    assert not result.ok, expr + " 在 examples/bad 上应当失败（否则断言形同虚设）"


def test_exit_form_is_not_always_true(good):
    assert evaluate("exit:0", good).ok
    assert not evaluate("exit:1", good).ok, "exit:1 在退出码 0 的运行上不该通过"


def test_every_documented_form_is_covered_here():
    """llms.txt 列了哪些形式，这份测试就要覆盖哪些 —— 防止文档加了新语法而没人验。"""
    text = (REPO / "llms.txt").read_text(encoding="utf-8")
    forms = set(re.findall(r"`([a-z]+):", text))
    assert {"before", "tool", "never", "touched", "exit"} <= forms, "llms.txt 里少了语法？"
    source = Path(__file__).read_text(encoding="utf-8")
    for form in ("before:", "tool:", "never:", "touched:", "exit:"):
        assert form in source, "测试没覆盖这种形式：" + form


def test_unknown_form_is_refused_loudly(good):
    with pytest.raises(Exception):
        evaluate("nonsense:whatever", good)
