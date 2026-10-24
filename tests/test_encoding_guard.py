"""编码守则：任何会打印非 ASCII 的 tools/*.py 必须自己钉 UTF-8。

为什么要有这条测试：同一个坑已经踩了两次（validate_cassette 之后，cassette_view 和 dogfood
各漏一次）。「Linux CI 看不出来、Windows 上乱码」这类 bug 不会自己暴露，只能靠规则拦。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"


def _has_non_ascii(text: str) -> bool:
    return any(ord(ch) > 127 for ch in text)


def _pins_utf8(text: str) -> bool:
    return "_force_utf8" in text or 'reconfigure(encoding="utf-8"' in text


def test_every_printing_tool_pins_its_own_stdout_encoding():
    offenders = []
    for path in sorted(TOOLS.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not (_has_non_ascii(text) and "print(" in text):
            continue
        if not _pins_utf8(text):
            offenders.append(path.name)
    assert offenders == [], "这些脚本会按系统代码页输出，CI/父进程按 utf-8 读就是乱码：" + ", ".join(offenders)


def test_the_guard_actually_works_when_the_env_is_hostile():
    """剥掉 PYTHONIOENCODING / PYTHONUTF8，按 utf-8 解码必须读得通。"""
    import os

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONIOENCODING", "PYTHONUTF8"}}
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "dogfood.py")],
        cwd=str(REPO), capture_output=True, env=env,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    assert "噪声条数" in proc.stdout.decode("utf-8")
