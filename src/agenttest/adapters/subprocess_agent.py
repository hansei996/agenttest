"""跑一个真实的 CLI agent，并把它的一次运行录成 cassette。

观测边界（写进 run.start.meta，可核验）：

| 事实 | 从哪来 |
|---|---|
| argv / cwd | 调用方给的东西 |
| 退出码 / 耗时 | subprocess 的返回值与秒表 |
| stdout / stderr | 捕获后截断到 stream_limit，截断与否记在 meta |
| 被改动的文件 | 跑之前和跑之后各对工作目录做一次 sha256 快照，取差集 |
| 模型调用、工具调用 | **只有在 agent 自己吐 JSONL 时才有**，否则不存在 |

文件改动为什么用 sha256 前后对比，而不是 git status：

* 不要求在 git 仓库里跑——很多 agent 在临时目录、容器挂载点里工作。
* 不依赖 git 二进制与 .gitignore 的写法；git status 还会把"上一次运行留下的
  未跟踪文件"和"这次的新文件"混在一起。
* 与 run.end.files 用的是同一套 sha256，replay 的产物校验可以直接复用。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import events as ev
from ..cassette import write_cassette

DEFAULT_STREAM_LIMIT = 4000
MAX_SCAN_FILES = 5000
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
}
ENVELOPE_TYPES = ("run.start", "run.end")


class AdapterError(RuntimeError):
    """被测 agent 起不来、超时，或调用方给错了参数。"""


@dataclass
class SubprocessOutcome:
    target: str
    cassette: str
    events: list = field(default_factory=list)
    events_source: str = ""
    unobserved: list = field(default_factory=list)
    exit_code: int = 0
    duration: float = 0.0
    stdout: str = ""
    stderr: str = ""
    files_changed: list = field(default_factory=list)

    @property
    def counts(self) -> dict:
        counts: dict = {}
        for event in self.events:
            counts[event["type"]] = counts.get(event["type"], 0) + 1
        return counts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_tree(root: Path, limit: int = MAX_SCAN_FILES) -> tuple:
    """给工作目录做一次快照：{相对路径: sha256}。返回 (快照, 是否被上限截断)。"""
    state: dict = {}
    if not root.is_dir():
        return state, False
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not path.is_file():
                continue
            seen += 1
            if seen > limit:
                return state, True
            try:
                state[path.relative_to(root).as_posix()] = _sha256_file(path)
            except OSError:
                continue
    return state, False


def diff_snapshots(before: dict, after: dict) -> tuple:
    """取差集：返回 (改动路径, {路径: 新哈希或 None}, 计数)。"""
    changed: list = []
    files: dict = {}
    counts = {"created": 0, "modified": 0, "deleted": 0}
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        if old == new:
            continue
        changed.append(path)
        files[path] = new
        if new is None:
            counts["deleted"] += 1
        elif old is None:
            counts["created"] += 1
        else:
            counts["modified"] += 1
    return changed, files, counts


def parse_stdout_events(text: str) -> tuple:
    """解析 stdout 上的 JSONL 事件流。返回 (事件列表或 None, 原因)。

    只有"非空行全是带 type 的 JSON 对象、且每条都过事件校验"才算事件流。
    任何一行不合格就整体退回 os_observation——绝不挑着用。
    """
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return None, "stdout 是空的"
    collected: list = []
    for index, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except ValueError:
            return None, "第 " + str(index) + " 行不是 JSON"
        if not isinstance(value, dict) or "type" not in value:
            return None, "第 " + str(index) + " 行不是带 type 字段的 JSON 对象"
        collected.append(value)
    for index, event in enumerate(collected, start=1):
        try:
            ev.validate(event)
        except ev.EventError as exc:
            return None, "第 " + str(index) + " 行的事件不合法：" + str(exc)
    return collected, ""


def _truncate(text: str, limit: int) -> tuple:
    text = text or ""
    if limit is None or limit <= 0 or len(text) <= limit:
        return text, False
    head = text[:limit]
    return head + "\n…（已截断：原长 " + str(len(text)) + " 字符，上限 " + str(limit) + "）", True


def record_subprocess(
    argv,
    out_dir,
    *,
    cwd=None,
    env=None,
    timeout=None,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    watch=None,
):
    """跑一次 argv，把这次运行录成 <out_dir>/cassette.jsonl。

    argv        要跑的命令（列表，不做 shell 解析）
    out_dir     cassette 输出目录
    cwd         子进程工作目录（也是文件改动的观测根，除非另给 watch）
    env         额外的环境变量，覆盖 os.environ 里的同名项
    timeout     秒；超时抛 AdapterError（进程会被杀掉），不会挂死
    stream_limit stdout/stderr 各保留多少字符
    watch       比较文件改动的工作目录，默认等于 cwd
    """
    if not argv:
        raise AdapterError("record_subprocess 需要一个要跑的命令：argv 不能为空")
    command = [str(item) for item in argv]
    workdir = Path(cwd).resolve() if cwd else Path.cwd()
    if not workdir.is_dir():
        raise AdapterError("cwd 不是一个目录：" + str(workdir))
    watched = Path(watch).resolve() if watch else workdir
    if not watched.is_dir():
        raise AdapterError("watch 不是一个目录：" + str(watched))
    if stream_limit is not None and stream_limit < 0:
        raise AdapterError("stream_limit 不能是负数：" + str(stream_limit))
    if timeout is not None and timeout <= 0:
        raise AdapterError("timeout 必须大于 0 秒：" + str(timeout))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    child_env = os.environ.copy()
    if env:
        child_env.update({str(key): str(value) for key, value in env.items()})

    before, capped_before = snapshot_tree(watched)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(workdir),
            env=child_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        tail, _ = _truncate(_as_text(exc.stderr), stream_limit)
        raise AdapterError(
            "被测 agent 超时：超过 "
            + ("%.3fs" % timeout if timeout is not None else "时限")
            + " 没有结束，已终止进程（"
            + " ".join(command)
            + "，跑了 %.3fs）。" % elapsed
            + ("它最后写到 stderr 的内容：\n" + tail.strip()[-800:] if tail.strip() else "它没有写出任何 stderr。")
            + "\n如果是正常的长时间任务，用 --timeout 放大上限。"
        ) from exc
    except OSError as exc:
        raise AdapterError(
            "起不来被测 agent：" + repr(command) + "：" + str(exc)
            + "。检查可执行文件是否存在、是否在 PATH 上。"
        ) from exc

    duration = round(time.monotonic() - started, 4)
    after, capped_after = snapshot_tree(watched)
    changed, files, counts = diff_snapshots(before, after)

    stdout, stdout_truncated = _truncate(proc.stdout, stream_limit)
    stderr, stderr_truncated = _truncate(proc.stderr, stream_limit)

    agent_events, stdout_note = parse_stdout_events(proc.stdout)
    envelope_dropped = 0
    body: list = []
    if agent_events is None:
        events_source = "os_observation"
    else:
        events_source = "agent_stdout"
        for event in agent_events:
            if event.get("type") in ENVELOPE_TYPES:
                envelope_dropped += 1
                continue
            body.append(event)

    seen = {event.get("type") for event in body}
    unobserved = [name for name in ev.EVENT_TYPES if name not in seen and name not in ENVELOPE_TYPES]

    meta = {
        "cassette_kind": "subprocess_agent",
        "events_source": events_source,
        "envelope_source": "adapter",
        "envelope_dropped": envelope_dropped,
        "unobserved": unobserved,
        "exit_code": int(proc.returncode),
        "duration_s": duration,
        "stdout": stdout,
        "stdout_truncated": stdout_truncated,
        "stderr": stderr,
        "stderr_truncated": stderr_truncated,
        "stream_limit": stream_limit,
        "timeout_s": timeout,
        "files_detection": "sha256_before_after",
        "files_observed": counts,
        "snapshot_files": len(after),
        "snapshot_capped": bool(capped_before or capped_after),
        "watch": watched.as_posix(),
    }
    if events_source == "os_observation":
        meta["stdout_note"] = "stdout 不是 JSONL 事件流：" + stdout_note
    else:
        meta["stdout_note"] = "stdout 是 JSONL 事件流，采用了其中的 " + str(len(body)) + " 条 agent 自报事件"

    start = {
        "type": "run.start",
        "agent": "subprocess:" + Path(command[0]).name,
        "argv": command,
        "cwd": workdir.as_posix(),
        "env_fingerprint": ev.env_fingerprint(),
        "workdir": ".",
        "t": 0.0,
        "meta": meta,
    }
    end = {
        "type": "run.end",
        "exit_code": int(proc.returncode),
        "files_changed": changed,
        "files": files,
        "t": duration,
    }

    events = [start] + body + [end]
    for event in events:
        ev.validate(event)
    path = write_cassette(out, events)
    return SubprocessOutcome(
        target=str(out_dir),
        cassette=str(path),
        events=events,
        events_source=events_source,
        unobserved=unobserved,
        exit_code=int(proc.returncode),
        duration=duration,
        stdout=stdout,
        stderr=stderr,
        files_changed=changed,
    )


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def summarize(outcome: SubprocessOutcome) -> str:
    """给人看的录制摘要（CLI 直接打印它）。"""
    parts = ", ".join(name + " " + str(count) for name, count in outcome.counts.items())
    label = "os_observation（进程层观测）" if outcome.events_source == "os_observation" else "agent_stdout（采用 agent 自报的 JSONL 事件）"
    lines = [
        "recorded " + outcome.target + " -> " + outcome.cassette,
        "  " + str(len(outcome.events)) + " 个事件（" + parts + "）",
        "  事件来源  " + label,
        "  未观测    " + (", ".join(outcome.unobserved) if outcome.unobserved else "（6 类事件都观测到了）"),
        "  退出码    " + str(outcome.exit_code) + " · 耗时 %.3fs" % outcome.duration,
        "  改动文件  " + (", ".join(outcome.files_changed) if outcome.files_changed else "（无）"),
    ]
    return "\n".join(lines)
