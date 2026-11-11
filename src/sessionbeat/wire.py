"""Log wire format. Standard library only: the hook imports this and must start fast."""

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class Kind(StrEnum):
    SESSION_STARTED = "session_started"
    TURN_ENDED = "turn_ended"
    TURN_FAILED = "turn_failed"
    PERMISSION_ASKED = "permission_asked"
    TOOL_FINISHED = "tool_finished"
    USER_ANSWERED = "user_answered"
    GOAL_SET = "goal_set"
    PLAN_SET = "plan_set"
    STEP_STARTED = "step_started"
    STEPS_DONE = "steps_done"
    CHECK_RAN = "check_ran"
    TERM_DEFINED = "term_defined"
    CARD_WRITTEN = "card_written"


class AgentName(StrEnum):
    CLAUDE_CODE = "claude-code"


SESSION_ENV: dict[AgentName, str] = {AgentName.CLAUDE_CODE: "CLAUDE_CODE_SESSION_ID"}

SHORT_TEXT_MAX = 120
CARD_TEXT_MAX = 240
LABEL_MAX = 16
PLAN_STEPS_MAX = 12
HOOK_TEXT_MAX = 300
CONTROL_CHAR_CLASS = r"\x00-\x1f\x7f-\x9f"

_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def home() -> Path:
    override = os.environ.get("SESSIONBEAT_HOME")
    if override is not None:
        path = Path(override)
        if not path.is_absolute():
            raise ValueError(f"SESSIONBEAT_HOME must be an absolute path, got {override!r}")
        return path
    return Path.home() / ".sessionbeat"


def session_log_path(session_id: str) -> Path:
    # The id comes from outside the process; this check keeps it from escaping the sessions dir.
    if not _SESSION_ID.fullmatch(session_id):
        raise ValueError(f"Invalid session id {session_id!r}: must match {_SESSION_ID.pattern}")
    return home() / "sessions" / f"{session_id}.jsonl"


def _make_log_dir(path: Path) -> None:
    # `parents=True` applies the mode to the leaf only, so each level is created explicitly.
    home().mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.mkdir(mode=0o700, exist_ok=True)


@contextmanager
def locked_log(session_id: str) -> Iterator[None]:
    """Hold the session log's exclusive lock; closing the descriptor releases it."""
    path = session_log_path(session_id)
    _make_log_dir(path)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def append_record(
    session_id: str,
    agent: AgentName,
    kind: Kind,
    fields: dict[str, object],
    at: datetime,
) -> None:
    path = session_log_path(session_id)
    line = (
        json.dumps({"at": at.isoformat(), "agent": agent, "kind": kind, **fields}) + "\n"
    ).encode("utf-8")
    _make_log_dir(path)
    # One os.write on an O_APPEND descriptor: concurrent writers cannot interleave inside a line.
    # A short write leaves a torn line that the next append would join onto, so it is an error.
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        written = os.write(fd, line)
    finally:
        os.close(fd)
    if written != len(line):
        raise OSError(f"Short write to {path}: wrote {written} of {len(line)} bytes")


def cut(text: str) -> tuple[str, bool]:
    if len(text) <= HOOK_TEXT_MAX:
        return text, False
    return text[:HOOK_TEXT_MAX], True


def input_key(tool_input: object) -> str:
    canonical = json.dumps(tool_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
