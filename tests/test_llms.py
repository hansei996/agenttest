"""llms.txt 与错误索引：链接必须存在，事实必须与本仓库一致。"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _links(text: str) -> list[str]:
    return re.findall(r"\]\((\./[^)]+)\)", text)


def test_llms_txt_exists_and_has_no_dead_links():
    path = REPO / "llms.txt"
    assert path.exists(), "llms.txt 是给 AI 检索的入口，删了就等于关掉一条渠道"
    links = _links(path.read_text(encoding="utf-8"))
    assert links, "llms.txt 至少要指向 README 与格式规范"
    missing = [l for l in links if not (REPO / l).exists()]
    assert missing == [], "死链：" + ", ".join(missing)


def test_error_index_lists_every_error_page():
    index = (REPO / "docs" / "errors" / "index.md").read_text(encoding="utf-8")
    pages = sorted(p.name for p in (REPO / "docs" / "errors").glob("*.md") if p.name != "index.md")
    assert pages, "错误页一个都不剩了？"
    for name in pages:
        assert name in index, "索引里漏了：" + name


def test_llms_txt_quotes_the_same_statistics_as_the_code():
    """不许在 llms.txt 里编造数字：381 这个数与 runs_needed(0.99) 必须一致。"""
    from agenttest.flaky import runs_needed

    text = (REPO / "llms.txt").read_text(encoding="utf-8")
    assert str(runs_needed(0.99)) in text
    assert "0.23" not in text.replace("0.23–0.88", "")  # 区间只能以真实形式出现
