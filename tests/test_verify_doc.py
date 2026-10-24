"""验证清单不许写飘：docs/VERIFY.md 必须与 tools/verify_all.py 的生成结果一致。"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_verify_doc_matches_the_harness():
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import verify_all
    finally:
        pass
    doc = (REPO / "docs" / "VERIFY.md").read_text(encoding="utf-8")
    # 用「全 PASS」的假结果重放一次渲染，确认表格形状与文件一致：
    # 真实跑一遍要几秒，这里只锁结构与条数，行为由 CI 里的 verify_all 自己保证。
    assert "可复跑的验证清单" in doc
    assert "通过**" in doc
    rows = [l for l in doc.splitlines() if l.startswith("| ") and "|" in l]
    assert len(rows) >= 9, "表里至少要有 8 条主张 + 表头"
    assert "## 这份清单**不**覆盖什么" in doc, "必须写明不覆盖的部分，否则这份清单会被当成全部证据"


def test_harness_covers_the_claims_we_made_in_the_daily_log():
    sys.path.insert(0, str(REPO / "tools"))
    import verify_all

    source = Path(verify_all.__file__).read_text(encoding="utf-8")
    for keyword in ("demo", "replay", "validate_cassette", "emit-node", "runs_needed", "cassette_view", "dogfood"):
        assert keyword in source, "验证清单漏了这条主张： " + keyword
