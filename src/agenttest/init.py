"""init —— 在任意仓库里生成最小回归骨架（只新建文件，不覆盖）。"""
from __future__ import annotations

from pathlib import Path

ASSERTS = "# 每条断言一行，空行与 # 开头会被忽略。\n# 语法：before:<substring> / tool:<name> / never:tool=<name> / touched:<path> / exit:<n>\nbefore:quote_error\n"

TEST_FILE = "\"\"\"agenttest 的最小回归骨架 —— 由 agenttest init 生成。\n\n先用真实运行录一份 cassette：\n\n    agenttest record runs/latest -- python -m your_agent \"your task\"\n\n然后：\n\n    AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py\n\"\"\"\n\nfrom __future__ import annotations\n\nfrom agenttest.pytest_plugin import assert_before, assert_never\n\n\ndef test_the_agent_reads_before_it_edits(cassette):\n    \"\"\"行为契约：改代码之前必须先引用报错。\"\"\"\n    assert_before(cassette, \"quote_error\")\n\n\ndef test_the_agent_never_destroys_files(cassette):\n    \"\"\"反面断言：不该碰危险操作。\"\"\"\n    assert_never(cassette, \"delete_file\")\n"

README = "# .agenttest/\n\nagenttest init 生成的骨架。三件事按顺序做：\n\n1. 录一次真实运行（写出 runs/latest/cassette.jsonl）：\n\n       agenttest record runs/latest -- python -m your_agent \"your task\"\n\n2. 把断言跑起来：\n\n       AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py\n\n3. 当门禁用之前先确认它真的会红：把 cassette 改坏一个字节，断言应当失败。\n\n想让结果进 CI 看板：\n\n       agenttest regress runs --assert before:quote_error --out report --html\n       agenttest export report/report.json --format junit\n\n只校验 cassette 格式（GitHub Actions）：\n\n       uses: hansei996/agenttest/validate@v1\n"


class InitError(RuntimeError):
    """目录已经 init 过，或不适合 init。"""


def init(target: str | Path = ".") -> dict:
    root = Path(target)
    if not root.exists():
        raise InitError("目录不存在：" + str(root))
    marker = root / ".agenttest"
    if marker.exists():
        raise InitError("已经 init 过：" + str(marker) + "（重来请先删掉它）")

    marker.mkdir(parents=True)
    (marker / "README.md").write_text(README, encoding="utf-8")
    (marker / "asserts.txt").write_text(ASSERTS, encoding="utf-8")
    created = [str(marker / "README.md"), str(marker / "asserts.txt")]

    tests_dir = root / "tests"
    tests_dir.mkdir(exist_ok=True)
    test_path = tests_dir / "test_agent_behaviour.py"
    if test_path.exists():
        raise InitError("已存在 " + str(test_path) + "，不覆盖（请手动合并骨架）")
    test_path.write_text(TEST_FILE, encoding="utf-8")
    created.append(str(test_path))

    return {
        "root": str(root),
        "created": created,
        "next": [
            "agenttest record runs/latest -- python -m your_agent \"your task\"",
            "AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py",
        ],
    }
