"""pytest 插件：cassette fixture + 断言助手（复用 assertions 语义，不另造判定）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agenttest import assertions as asrt
from agenttest import pytest_plugin as pp
from agenttest.cassette import CassetteError

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

# 子进程里跑的"用户测试"：就是文档里让人抄的那三行。
INNER_TEST = """from agenttest.pytest_plugin import assert_before, assert_never, assert_tool


def test_agent_reads_logs_first(cassette):
    assert_before(cassette, "quote_error")
    assert_tool(cassette, "read_file", path="src/auth.py")
    assert_never(cassette, "delete_file")
"""


def pytest_env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env.pop(pp.ENV_VAR, None)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else str(SRC) + os.pathsep + existing
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


def plugin_args() -> list:
    """装了包就让 entry point 自己加载插件；没装就手动 -p，两种情况下测试都可跑。"""
    if registered_entry_points():
        return []
    return ["-p", "agenttest.pytest_plugin"]


def registered_entry_points():
    from importlib.metadata import entry_points

    return [ep for ep in entry_points(group="pytest11") if ep.name == "agenttest"]


def run_pytest_in(tmp_path: Path, *args: str, extra_env: dict | None = None):
    (tmp_path / "test_inner.py").write_text(INNER_TEST, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *plugin_args(),
            "test_inner.py",
            "-q",
            *args,
        ],
        cwd=str(tmp_path),
        env=pytest_env(extra_env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_good_cassette_passes_all_three_helpers(examples):
    cassette = pp.load_cassette(examples / "good")
    pp.assert_before(cassette, "quote_error")
    pp.assert_tool(cassette, "read_file", path="src/auth.py")
    pp.assert_never(cassette, "delete_file")
    assert len(cassette) == 20
    assert cassette.path.name == "cassette.jsonl"


def test_bad_cassette_fails_before_at_the_edit_event(examples):
    cassette = pp.load_cassette(examples / "bad")
    with pytest.raises(pp.AgentTestAssertionError) as caught:
        pp.assert_before(cassette, "quote_error")
    message = str(caught.value)
    assert "FAIL before:quote_error" in message
    assert "第 4 个事件就是 edit_file(src/auth.py)" in message
    assert "全程没有引用过报错 quote_error" in message
    assert "cassette.jsonl" in message
    assert caught.value.expr == "before:quote_error"


def test_bad_cassette_fails_tool_helper_with_cli_wording(examples):
    cassette = pp.load_cassette(examples / "bad")
    with pytest.raises(pp.AgentTestAssertionError) as caught:
        pp.assert_tool(cassette, "read_file", path="logs/app.log")
    message = str(caught.value)
    assert "FAIL tool:read_file(path=logs/app.log)" in message
    assert "期望调用过 read_file(logs/app.log)" in message
    assert "实际工具调用序列是" in message


def test_never_helper_points_at_the_offending_event(examples):
    cassette = pp.load_cassette(examples / "bad")
    with pytest.raises(pp.AgentTestAssertionError) as caught:
        pp.assert_never(cassette, "edit_file")
    assert "第 4 个事件调用了 edit_file(src/auth.py)" in str(caught.value)


def test_helper_messages_are_the_assertions_module_originals(examples):
    """判定语义只有一套：助手的失败首行必须逐字等于 assertions.evaluate 的结果。"""
    cassette = pp.load_cassette(examples / "bad")
    direct = asrt.evaluate("before:quote_error", cassette.events)
    assert direct.ok is False
    with pytest.raises(pp.AgentTestAssertionError) as caught:
        pp.assert_before(cassette, "quote_error")
    assert str(caught.value).split("\n")[0] == direct.message


def test_missing_cassette_names_the_path(tmp_path):
    with pytest.raises(CassetteError) as caught:
        pp.load_cassette(tmp_path / "nope")
    assert "找不到 cassette" in str(caught.value)


def test_cassette_fixture_reads_the_env_var(monkeypatch, request, examples):
    monkeypatch.setenv(pp.ENV_VAR, str(examples / "good"))
    cassette = request.getfixturevalue("cassette")
    pp.assert_before(cassette, "quote_error")


class _ConfigWithoutCassette:
    """只提供 _cassette_target 需要的那两样东西：rootpath / getoption。"""

    rootpath = REPO

    def getoption(self, name, default=None):
        return default


def test_cassette_target_without_option_or_env_says_how_to_fix(monkeypatch):
    monkeypatch.delenv(pp.ENV_VAR, raising=False)
    with pytest.raises(BaseException, match="没有指定 cassette"):
        pp._cassette_target(_ConfigWithoutCassette())


def test_cassette_target_resolves_relative_paths_against_rootpath(monkeypatch):
    monkeypatch.setenv(pp.ENV_VAR, "examples/good")
    target = pp._cassette_target(_ConfigWithoutCassette())
    assert target == REPO / "examples" / "good"
    assert pp.load_cassette(target).path.name == "cassette.jsonl"


def test_plugin_is_registered_through_the_pytest11_entry_point():
    found = registered_entry_points()
    assert found, (
        "agenttest 没有注册 pytest11 入口点，pytest 找不到 cassette fixture："
        "先跑 python -m pip install -e . 再跑测试"
    )
    assert found[0].value == "agenttest.pytest_plugin"


def test_import_without_pytest_explains_the_fix(repo):
    code = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'pytest' or name.startswith('pytest.'):\n"
        "            raise ImportError('pytest blocked by test')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "try:\n"
        "    import agenttest.pytest_plugin\n"
        "except ImportError as exc:\n"
        "    print('ERROR:' + str(exc))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo),
        env=pytest_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert "ERROR:" in proc.stdout, proc.stdout + proc.stderr
    assert "pip install pytest" in proc.stdout
    assert "运行时本身不依赖 pytest" in proc.stdout


def test_pytest_option_loads_the_good_cassette(tmp_path, examples):
    proc = run_pytest_in(tmp_path, pp.OPTION + "=" + str(examples / "good"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout


def test_pytest_env_loads_the_bad_cassette_and_fails_at_the_expected_event(tmp_path, examples):
    proc = run_pytest_in(tmp_path, extra_env={pp.ENV_VAR: str(examples / "bad")})
    output = proc.stdout + proc.stderr
    assert proc.returncode == 1, output
    assert "FAIL before:quote_error" in output
    assert "第 4 个事件就是 edit_file(src/auth.py)" in output
    assert "1 failed" in output


def test_pytest_without_a_cassette_fails_with_a_usable_message(tmp_path):
    proc = run_pytest_in(tmp_path)
    output = proc.stdout + proc.stderr
    assert proc.returncode != 0, output
    assert "没有指定 cassette" in output
    assert pp.ENV_VAR in output
