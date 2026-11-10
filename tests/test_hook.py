import json
import os
import subprocess
import sys

from sessionbeat.board import Board, TurnFailedState
from sessionbeat.eventlog import read_events
from sessionbeat.wire import session_log_path


def run_hook(payload, home):
    env = {**os.environ, "SESSIONBEAT_HOME": str(home)}
    subprocess.run(
        [sys.executable, "-m", "sessionbeat.hook", "claude-code"],
        input=json.dumps(payload),
        text=True,
        env=env,
        check=True,
    )


def test_payload_sequence_becomes_board(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSIONBEAT_HOME", str(tmp_path))
    base = {"session_id": "s1", "cwd": "/repo"}
    bash = {"command": "ls"}
    write = {"file_path": "/repo/a.py", "content": "x"}
    payloads = [
        {**base, "hook_event_name": "SessionStart", "source": "startup"},
        {**base, "hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": bash},
        {**base, "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": bash},
        {**base, "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": write},
        {
            **base,
            "hook_event_name": "Stop",
            "last_assistant_message": "done \ud83d half",
            "background_tasks": [{"description": "dev server"}],
        },
        {**base, "hook_event_name": "UserPromptSubmit", "prompt": "next"},
        {
            **base,
            "hook_event_name": "StopFailure",
            "error": "rate_limit",
            "last_assistant_message": "oops",
        },
        {**base, "hook_event_name": "PreCompact"},
    ]
    for payload in payloads:
        run_hook(payload, tmp_path)

    events = read_events(session_log_path("s1"))
    board = Board.from_events("s1", events)
    assert len(events) == 7
    assert not board.pending_permissions
    assert "/repo/a.py" in board.edited_files
    assert isinstance(board.turn, TurnFailedState)


def test_hook_does_not_import_pydantic():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sessionbeat.hook, sys; "
            "banned = ['pydantic', *(f'sessionbeat.{m}' for m in "
            "('events', 'board', 'eventlog', 'cli', 'show'))]; "
            "print([m for m in banned if m in sys.modules])",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"
