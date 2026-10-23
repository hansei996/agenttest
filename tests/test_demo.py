"""demo 命令的冒烟测试：一条命令跑完必须自证成功。"""

from agenttest import demo


def test_demo_returns_zero_and_mentions_both_outcomes(capsys):
    code = demo.run_demo()
    out = capsys.readouterr().out
    assert code == 0
    assert "replay examples/good" in out
    assert "replay examples/bad" in out
    assert "FAIL" in out
    assert "第 4 个事件" in out or "没引用过报错" in out
