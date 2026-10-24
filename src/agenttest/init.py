"""init —— 在任意仓库里生成最小回归骨架（只新建文件，不覆盖）。"""
from __future__ import annotations

from pathlib import Path

ASSERTS = "before:quote_error\n"

TEST_FILE = "\"\"\"agenttest 的最小回归骨架 —— 由 agenttest init 生成。\n\n三条录制路径，按你的 agent 情况选一条：\n\n  # 1) 最通用：任何 CLI agent，不用改一行代码\n  agenttest record-subprocess runs/latest -- python -m your_agent \"your task\"\n\n  # 2) 你的 agent 已经用 agenttest.agent.Session 说话时\n  agenttest record runs/latest -- python -m your_agent \"your task\"\n\n  # 3) 你手上已有 OpenAI / Anthropic 的日志\n  agenttest import logs/run.jsonl runs/latest\n\n然后：\n\n    AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py\n\"\"\"\n\nfrom __future__ import annotations\n\nimport pytest\n\nfrom agenttest.assertions import evaluate\nfrom agenttest.pytest_plugin import AgentTestAssertionError, assert_never\n\n\ndef _check(cassette, expr: str):\n    result = evaluate(expr, cassette.events)\n    if not result.ok:\n        raise AgentTestAssertionError(result.message)\n    return result\n\n\ndef test_the_agent_exits_cleanly(cassette):\n    \"\"\"任何 cassette 都能断言这条（包括 record-subprocess 的进程层观测）。\"\"\"\n    _check(cassette, \"exit:0\")\n\n\ndef test_the_agent_never_destroys_files(cassette):\n    \"\"\"反面断言：不该碰危险操作。\"\"\"\n    assert_never(cassette, \"delete_file\")\n\n\ndef test_the_agent_reads_before_it_edits(cassette):\n    \"\"\"行为契约：改代码前必须先引用报错。\n\n    这条需要「有模型事件」的 cassette（record 或 import 产出的）。\n    record-subprocess 只做进程层观测、看不到 model.result，所以这里自动跳过而不是假装失败。\n    \"\"\"\n    if not any(event.get(\"type\") == \"model.result\" for event in cassette.events):\n        pytest.skip(\"这份 cassette 没有 model 事件（进程层观测）；before: 断言需要 record 或 import 产出的 cassette\")\n    _check(cassette, \"before:quote_error\")\n"

README = "# .agenttest/\n\nagenttest init 生成的骨架。按顺序做三件事：\n\n1. 录一次真实运行。先看你的 agent 属于哪一种：\n\n       最通用（任何 CLI agent，不用改代码）：\n           agenttest record-subprocess runs/latest -- python -m your_agent \"your task\"\n\n       agent 已用 agenttest.agent.Session 说话：\n           agenttest record runs/latest -- python -m your_agent \"your task\"\n\n       手上已有 OpenAI / Anthropic 日志：\n           agenttest import logs/run.jsonl runs/latest\n\n   注意：record-subprocess 只做进程层观测，看不到 model.result / tool.call，\n   所以「改代码前先引用报错」那条断言会自动跳过（而不是报错）——\n   要用它，改走 record 或 import。\n\n2. 把断言跑起来：\n\n       AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py\n\n3. 当门禁用之前先确认它真的会红：把 cassette 改坏一个字节，断言应当失败。\n\n想让结果进 CI 看板：\n\n       agenttest regress runs --assert exit:0 --out report --html\n       agenttest export report/report.json --format junit\n\n只校验 cassette 格式（GitHub Actions）：\n\n       uses: hansei996/agenttest/validate@v1\n"


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
            "agenttest record-subprocess runs/latest -- python -m your_agent \"your task\"",
            "AGENTTEST_CASSETTE=runs/latest pytest tests/test_agent_behaviour.py",
        ],
    }
