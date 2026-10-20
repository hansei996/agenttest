"""adapters：把真实 CLI agent 的一次运行录成 cassette。

四条硬要求都在这里守：cassette 能过 tools/validate_cassette.py、退出码/耗时/改动
文件被真实记录、meta.unobserved 诚实列出看不见的事件类型、超时给清晰错误而不是挂死。
另外守住"不许编造"：只有 agent 自己吐 JSONL 时才会出现 model.call / tool.call。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agenttest import events as ev
from agenttest.adapters import AdapterError, record_subprocess
from agenttest.cassette import read_cassette

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
VALIDATOR = REPO / "tools" / "validate_cassette.py"
INVISIBLE = ["model.call", "model.result", "tool.call", "tool.result"]


def child_env(**extra) -> dict:
    """子进程环境：让 examples/fake_agent.py 能 import agenttest 并正常跑。"""
    env = {
        "PYTHONPATH": str(SRC),
        "PYTHONIOENCODING": "utf-8",
    }
    env.update(extra)
    return env


def write_agent(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def run_validator(target: Path) -> subprocess.CompletedProcess:
    """真的跑一次校验器（不是 import 它的函数）。"""
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def fake_agent_run(tmp_path: Path, out: Path, script: str = "good"):
    """用仓库自带的 examples/fake_agent.py 当被测 CLI。

    它需要 agenttest 的 Session 环境变量才能跑（那是它自己的实现细节），
    把事件写到一个临时文件里即可；stdout 上没有任何 JSONL，所以适配器仍然
    只能走 os_observation —— 这正是要验证的路径。
    """
    shutil.rmtree(REPO / "examples" / ".work", ignore_errors=True)
    events_file = tmp_path / "child-events.jsonl"
    env = child_env(
        AGENTTEST_MODE="record",
        AGENTTEST_EVENTS=str(events_file.resolve()),
    )
    return record_subprocess(
        [sys.executable, str(REPO / "examples" / "fake_agent.py"), "--script", script],
        out,
        cwd=REPO,
        env=env,
        timeout=120,
    )


# -- ① cassette 合法、能过独立校验器 -------------------------------------


def test_fake_agent_cassette_passes_the_standalone_validator(tmp_path):
    out = tmp_path / "run1"
    outcome = fake_agent_run(tmp_path, out)
    assert Path(outcome.cassette).is_file()
    proc = run_validator(out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS（12 条规则全部通过）" in proc.stdout
    # 读回来自证：哈希链完整 + 首尾是 run.start / run.end
    events = read_cassette(out)
    assert events[0]["type"] == "run.start"
    assert events[-1]["type"] == "run.end"


# -- ② 退出码 / 耗时 / 改动文件 ------------------------------------------


def test_exit_code_duration_and_changed_files_are_recorded(tmp_path):
    out = tmp_path / "run2"
    outcome = fake_agent_run(tmp_path, out)
    assert outcome.exit_code == 0
    assert outcome.duration > 0
    assert "examples/.work/good/src/auth.py" in outcome.files_changed
    events = read_cassette(out)
    end = events[-1]
    assert end["exit_code"] == 0
    assert end["t"] == pytest.approx(outcome.duration, abs=1e-6)
    assert "examples/.work/good/src/auth.py" in end["files_changed"]
    # 产物哈希进 run.end.files，且与磁盘上的真实内容一致
    recorded = end["files"]["examples/.work/good/src/auth.py"]
    assert recorded and len(recorded) == 64
    on_disk = (REPO / "examples" / ".work" / "good" / "src" / "auth.py").read_bytes()
    import hashlib

    assert hashlib.sha256(on_disk).hexdigest() == recorded


def test_agent_that_crashes_is_recorded_rather_than_hidden(tmp_path):
    """跑不通也是行为：退出码和 stderr 都留下，不抛异常、不假装成功。"""
    out = tmp_path / "crashed"
    outcome = record_subprocess(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"],
        out,
        cwd=tmp_path,
    )
    assert outcome.exit_code == 3
    assert "boom" in outcome.stderr
    events = read_cassette(out)
    assert events[-1]["exit_code"] == 3
    assert events[0]["meta"]["stderr"].startswith("boom")


# -- ③ meta.unobserved 诚实列出没观测到的类型 ----------------------------


def test_unobserved_lists_every_invisible_event_type(tmp_path):
    out = tmp_path / "run3"
    outcome = fake_agent_run(tmp_path, out)
    start = read_cassette(out)[0]
    assert start["meta"]["events_source"] == "os_observation"
    assert start["meta"]["unobserved"] == INVISIBLE
    assert outcome.events_source == "os_observation"
    # 看不见的类型一条都不许出现在事件流里
    present = {event["type"] for event in read_cassette(out)}
    assert present == {"run.start", "run.end"}
    assert start["meta"]["stdout_note"].startswith("stdout 不是 JSONL 事件流")


def test_jsonl_events_from_stdout_are_used_and_shrink_unobserved(tmp_path):
    agent = write_agent(
        tmp_path / "jsonl_agent.py",
        "\n".join(
            [
                "import json, sys",
                "events = [",
                "    {'type': 'model.call', 'model': 'm', 'request': {'messages': [], 'tools': []}},",
                "    {'type': 'model.result', 'text': 'hi', 'tool_calls': [], 'usage': {'in': 1, 'out': 1}},",
                "    {'type': 'tool.call', 'name': 'read_file', 'args': {'path': 'a.txt'}},",
                "    {'type': 'tool.result', 'name': 'read_file', 'ok': True, 'bytes': 3},",
                "]",
                "for event in events:",
                "    sys.stdout.write(json.dumps(event) + chr(10))",
                "",
            ]
        ),
    )
    out = tmp_path / "stdout_events"
    outcome = record_subprocess([sys.executable, str(agent)], out, cwd=tmp_path)
    assert outcome.events_source == "agent_stdout"
    events = read_cassette(out)
    assert [event["type"] for event in events] == [
        "run.start",
        "model.call",
        "model.result",
        "tool.call",
        "tool.result",
        "run.end",
    ]
    assert events[0]["meta"]["unobserved"] == []
    assert events[0]["meta"]["envelope_source"] == "adapter"


def test_agent_cannot_forge_the_envelope(tmp_path):
    """agent 自报的 run.start / run.end 一律丢掉，argv 与退出码以观测为准。"""
    agent = write_agent(
        tmp_path / "forge.py",
        "\n".join(
            [
                "import json, sys",
                "fake = {'type': 'run.start', 'agent': 'liar', 'argv': ['rm', '-rf', '/'],",
                "        'cwd': '/nowhere', 'env_fingerprint': 'x'}",
                "sys.stdout.write(json.dumps(fake) + chr(10))",
                "sys.stdout.write(json.dumps({'type': 'run.end', 'exit_code': 0, 'files_changed': []}) + chr(10))",
                "sys.exit(7)",
                "",
            ]
        ),
    )
    out = tmp_path / "forged"
    outcome = record_subprocess([sys.executable, str(agent)], out, cwd=tmp_path)
    events = read_cassette(out)
    start = events[0]
    assert start["agent"] == "subprocess:" + Path(sys.executable).name
    assert start["argv"] == [sys.executable, str(agent)]
    assert start["meta"]["envelope_dropped"] == 2
    assert events[-1]["exit_code"] == 7


def test_mixed_stdout_falls_back_to_os_observation(tmp_path):
    agent = write_agent(
        tmp_path / "mixed.py",
        "import json, sys\n"
        "sys.stdout.write(json.dumps({'type': 'model.call', 'model': 'm', 'request': {}}) + chr(10))\n"
        "sys.stdout.write('this line is not json' + chr(10))\n",
    )
    out = tmp_path / "mixed_out"
    outcome = record_subprocess([sys.executable, str(agent)], out, cwd=tmp_path)
    assert outcome.events_source == "os_observation"
    start = read_cassette(out)[0]
    assert "第 2 行不是 JSON" in start["meta"]["stdout_note"]
    assert start["meta"]["unobserved"] == INVISIBLE


# -- ④ 超时：清晰错误，不挂死 --------------------------------------------


def test_timeout_raises_a_clear_error_instead_of_hanging(tmp_path):
    started = time.monotonic()
    with pytest.raises(AdapterError) as excinfo:
        record_subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "timeout",
            cwd=tmp_path,
            timeout=0.4,
        )
    elapsed = time.monotonic() - started
    assert elapsed < 15, "超时必须尽快返回，不能等满子进程"
    message = str(excinfo.value)
    assert "超时" in message
    assert "0.400" in message or "0.4" in message
    assert "--timeout" in message
    assert not (tmp_path / "timeout" / "cassette.jsonl").exists(), "超时不该写出半份 cassette"


def test_missing_executable_is_reported_not_crashed(tmp_path):
    with pytest.raises(AdapterError) as excinfo:
        record_subprocess(["definitely-not-a-real-binary-xyz"], tmp_path / "nope", cwd=tmp_path)
    assert "起不来被测 agent" in str(excinfo.value)


def test_bad_arguments_are_rejected(tmp_path):
    with pytest.raises(AdapterError):
        record_subprocess([], tmp_path / "empty")
    with pytest.raises(AdapterError):
        record_subprocess([sys.executable, "-c", "pass"], tmp_path / "t", cwd=tmp_path, timeout=0)


# -- 文件改动：增 / 改 / 删 都要看见 -------------------------------------


def test_file_creation_modification_and_deletion_are_all_detected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "keep.txt").write_text("same", encoding="utf-8")
    (work / "change.txt").write_text("before", encoding="utf-8")
    (work / "gone.txt").write_text("bye", encoding="utf-8")
    agent = write_agent(
        tmp_path / "editor.py",
        "from pathlib import Path\n"
        "Path('created.txt').write_text('new', encoding='utf-8')\n"
        "Path('change.txt').write_text('after', encoding='utf-8')\n"
        "Path('gone.txt').unlink()\n",
    )
    out = tmp_path / "edits"
    outcome = record_subprocess([sys.executable, str(agent)], out, cwd=work)
    assert outcome.files_changed == ["change.txt", "created.txt", "gone.txt"]
    end = read_cassette(out)[-1]
    assert end["files"].get("gone.txt") is None
    assert end["files"]["created.txt"] is not None
    meta = read_cassette(out)[0]["meta"]
    assert meta["files_observed"] == {"created": 1, "modified": 1, "deleted": 1}
    assert meta["files_detection"] == "sha256_before_after"


def test_stream_limit_truncates_and_says_so(tmp_path):
    agent = write_agent(
        tmp_path / "loud.py",
        "import sys\nsys.stdout.write('x' * 5000)\nsys.stderr.write('y' * 5000)\n",
    )
    out = tmp_path / "loud"
    record_subprocess([sys.executable, str(agent)], out, cwd=tmp_path, stream_limit=100)
    meta = read_cassette(out)[0]["meta"]
    assert meta["stdout_truncated"] is True
    assert meta["stderr_truncated"] is True
    assert len(meta["stdout"]) < 300
    assert "已截断" in meta["stdout"]
    assert meta["stream_limit"] == 100


# -- CLI 接线 ------------------------------------------------------------


def test_cli_record_subprocess_end_to_end(run, tmp_path):
    out = tmp_path / "cli-run"
    proc = run(
        "record-subprocess",
        str(out),
        "--",
        sys.executable,
        "-c",
        "print('cli ok')",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "事件来源  os_observation" in proc.stdout
    assert "未观测    model.call, model.result, tool.call, tool.result" in proc.stdout
    assert (out / "cassette.jsonl").is_file()
    assert run_validator(out).returncode == 0


def test_cli_accepts_options_after_the_target(run, tmp_path):
    """选项写在 target 之后也要能用（argparse 的 REMAINDER 会吞，CLI 自己切）。"""
    out = tmp_path / "cli-order"
    proc = run(
        "record-subprocess",
        str(out),
        "--stream-limit",
        "50",
        "--timeout",
        "60",
        "--",
        sys.executable,
        "-c",
        "print('ordered')",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    meta = read_cassette(out)[0]["meta"]
    assert meta["stream_limit"] == 50
    assert meta["timeout_s"] == 60.0


def test_cli_without_command_explains_itself(run, tmp_path):
    proc = run("record-subprocess", str(tmp_path / "empty"))
    assert proc.returncode == 1
    assert "record-subprocess 需要一个命令" in (proc.stdout + proc.stderr)


def test_cli_reports_timeout_cleanly(run, tmp_path):
    out = tmp_path / "cli-timeout"
    proc = run(
        "record-subprocess",
        str(out),
        "--timeout",
        "0.4",
        "--",
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
    )
    assert proc.returncode == 1
    assert "超时" in (proc.stdout + proc.stderr)
