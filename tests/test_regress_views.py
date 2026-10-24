"""regress --html 的下钻：每个 run 都能点进 cassette 查看器页面。"""
from __future__ import annotations

from pathlib import Path

from agenttest import regress as rg

REPO = Path(__file__).resolve().parents[1]


def test_html_links_each_run_to_its_own_view(tmp_path):
    report = rg.regress(REPO / "examples", asserts=["before:quote_error"], out=tmp_path / "rep", html=True, html_views=True)
    html = (tmp_path / "rep" / "index.html").read_text(encoding="utf-8")
    assert 'href="runs/good.html"' in html
    assert 'href="runs/bad.html"' in html
    assert (tmp_path / "rep" / "runs" / "good.html").exists()
    assert "run_views" in report.written


def test_the_linked_view_is_a_self_contained_page(tmp_path):
    rg.regress(REPO / "examples", asserts=["before:quote_error"], out=tmp_path / "rep2", html=True, html_views=True)
    page = (tmp_path / "rep2" / "runs" / "good.html").read_text(encoding="utf-8")
    assert "哈希链完好" in page
    assert "http://" not in page and "https://" not in page


def test_dashboard_still_works_without_the_viewer(tmp_path, monkeypatch):
    """tools/ 不在时（只装了 wheel）看板照常出，只是没有下钻链接 —— 不能整个报告失败。"""
    monkeypatch.setattr(rg, "write_run_views", lambda report, html_dir: {})
    rg.regress(REPO / "examples", asserts=["before:quote_error"], out=tmp_path / "rep3", html=True)
    html = (tmp_path / "rep3" / "index.html").read_text(encoding="utf-8")
    assert "runs/good.html" not in html
    assert "<td>good</td>" in html


def test_page_warns_when_it_depends_on_the_runs_directory(tmp_path):
    """单文件承诺的用法是「把 index.html 拷走」，而 --html-views 会让链接失效 —— 必须当场说清。"""
    rg.regress(REPO / "examples", asserts=["before:quote_error"], out=tmp_path / "a", html=True, html_views=True)
    with_views = (tmp_path / "a" / "index.html").read_text(encoding="utf-8")
    assert "下钻页" in with_views and "单独拷走" in with_views

    rg.regress(REPO / "examples", asserts=["before:quote_error"], out=tmp_path / "b", html=True)
    single = (tmp_path / "b" / "index.html").read_text(encoding="utf-8")
    assert "下钻页" not in single, "真正的单文件页面不该出现「依赖 runs/ 目录」这种警告"
