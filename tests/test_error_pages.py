"""错误页的「快速答案」块：必须靠前、必须简短、必须给出可执行动作。

为什么锁这个：搜索引擎（和 AI 摘要）取的是页面前几行里那段直答。
如果答案藏在第三节，这一页就只是个长文，救不了正在发痛的人。
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGES = sorted(p for p in (REPO / "docs" / "errors").glob("*.md") if p.name != "index.md")
MARK = "**快速答案**"


def test_every_error_page_has_a_direct_answer_near_the_top():
    assert len(PAGES) >= 3, "错误页少了？"
    for page in PAGES:
        lines = page.read_text(encoding="utf-8").splitlines()
        head = "\n".join(lines[:14])
        assert MARK in head, page.name + " 的前 14 行里没有快速答案块"


def test_the_answer_block_is_short_enough_to_be_a_snippet():
    for page in PAGES:
        lines = page.read_text(encoding="utf-8").splitlines()
        block = [l for l in lines[:16] if l.startswith(">")]
        assert block, page.name + " 没有引用块"
        text = "".join(block)
        assert len(text) <= 320, page.name + " 的快速答案太长（" + str(len(text)) + " 字）"


def test_the_answer_block_carries_a_concrete_number_or_command():
    """空话救不了人：块里必须出现数字或反引号命令。"""
    for page in PAGES:
        lines = page.read_text(encoding="utf-8").splitlines()
        text = "".join(l for l in lines[:16] if l.startswith(">"))
        has_command = "`" in text
        has_number = any(ch.isdigit() for ch in text)
        assert has_command or has_number, page.name + " 的快速答案既没有命令也没有数字"
