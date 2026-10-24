"""init：生成骨架、不覆盖、可被 pytest 直接跑。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agenttest.init import InitError, init


def test_init_creates_the_skeleton(tmp_path):
    result = init(tmp_path)
    assert (tmp_path / ".agenttest" / "README.md").exists()
    assert (tmp_path / ".agenttest" / "asserts.txt").exists()
    assert (tmp_path / "tests" / "test_agent_behaviour.py").exists()
    assert len(result["created"]) == 3


def test_init_refuses_to_run_twice(tmp_path):
    init(tmp_path)
    with pytest.raises(InitError):
        init(tmp_path)


def test_init_never_overwrites_an_existing_test_file(tmp_path):
    target = tmp_path / "tests" / "test_agent_behaviour.py"
    target.parent.mkdir(parents=True)
    target.write_text("# 我自己的测试\n", encoding="utf-8")
    with pytest.raises(InitError):
        init(tmp_path)
    assert target.read_text(encoding="utf-8") == "# 我自己的测试\n"


def test_generated_skeleton_imports_cleanly(tmp_path):
    init(tmp_path)
    generated = tmp_path / "tests" / "test_agent_behaviour.py"
    src = generated.read_text(encoding="utf-8")
    assert "from agenttest.pytest_plugin import" in src
    assert "record-subprocess" in src, "骨架必须指向真正能用的录制路径"
    assert "pytest.skip" in src, "没有 model 事件的 cassette 必须跳过而不是假装失败"
    # 只做语法检查，不执行（执行需要提供 cassette）
    compile(src, str(generated), "exec")