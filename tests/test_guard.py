"""网络守卫：replay 期间任何真实出网都必须被拦住。"""

from __future__ import annotations

import socket

import pytest

from agenttest import cassette as cas
from agenttest import guard
from agenttest.replay import ReplayError, replay


@pytest.fixture
def guarded():
    guard.install()
    try:
        yield
    finally:
        guard.uninstall()


def test_guard_blocks_tcp_connect(guarded):
    with pytest.raises(guard.NetworkBlockedError) as excinfo:
        socket.create_connection(("example.com", 80), timeout=1)
    assert "NETWORK GUARD" in str(excinfo.value)
    assert "example.com" in str(excinfo.value)


def test_guard_blocks_raw_socket_connect(guarded):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(guard.NetworkBlockedError):
            sock.connect(("1.1.1.1", 443))
    finally:
        sock.close()


def test_guard_blocks_urllib(guarded):
    import urllib.request

    with pytest.raises(guard.NetworkBlockedError):
        urllib.request.urlopen("http://example.com", timeout=1)


def test_guard_can_be_removed():
    guard.install()
    assert guard.is_installed() is True
    guard.uninstall()
    assert guard.is_installed() is False
    assert socket.create_connection.__name__ == "create_connection"


def test_replay_of_networked_agent_fails_with_guard_message(tmp_path):
    script = tmp_path / "netty.py"
    script.write_text(
        "import urllib.request\n"
        "from agenttest.agent import Session\n"
        "ctx = Session(agent='netty', workdir='.')\n"
        "urllib.request.urlopen('http://example.com', timeout=1)\n"
        "ctx.finish(exit_code=0, files_changed=[])\n",
        encoding="utf-8",
    )
    recorded = [
        {
            "t": 0.0,
            "type": "run.start",
            "agent": "netty",
            "argv": ["python", str(script)],
            "cwd": str(tmp_path),
            "env_fingerprint": "py3.12|test",
        },
        {"t": 0.1, "type": "run.end", "exit_code": 0, "files_changed": []},
    ]
    target = tmp_path / "netty-cassette"
    cas.write_cassette(target, recorded)
    with pytest.raises(ReplayError) as excinfo:
        replay(target)
    assert "网络守卫" in str(excinfo.value)
