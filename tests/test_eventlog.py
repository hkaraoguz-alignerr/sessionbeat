from datetime import UTC, datetime

import pytest

from sessionbeat.eventlog import read_events
from sessionbeat.events import GoalSet, SessionStarted, TurnEnded
from sessionbeat.wire import AgentName, Kind, append_record, session_log_path

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_round_trip_torn_line_and_invalid_line(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSIONBEAT_HOME", str(tmp_path))
    agent = AgentName.CLAUDE_CODE
    append_record("s1", agent, Kind.SESSION_STARTED, {"cwd": "/r", "source": "startup"}, NOW)
    append_record("s1", agent, Kind.GOAL_SET, {"text": "ship"}, NOW)
    append_record(
        "s1",
        agent,
        Kind.TURN_ENDED,
        {"last_message": "hi", "truncated": False, "background": None},
        NOW,
    )
    path = session_log_path("s1")
    events = read_events(path)
    assert [type(e) for e in events] == [SessionStarted, GoalSet, TurnEnded]
    assert events[0].at == NOW

    with path.open("ab") as f:
        f.write(b'{"at": "2026-01-01T12:00:00+00:00", "agent": "claude-')
    assert len(read_events(path)) == 3

    bad = tmp_path / "bad.jsonl"
    good = path.read_bytes().splitlines()[0]
    bad.write_bytes(good + b"\nnot json\n" + good + b"\n")
    with pytest.raises(ValueError, match=r"bad\.jsonl at line 2"):
        read_events(bad)


def test_session_log_path_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSIONBEAT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match=r"\.\./x"):
        session_log_path("../x")
    monkeypatch.setenv("SESSIONBEAT_HOME", "relative")
    with pytest.raises(ValueError, match="'relative'"):
        session_log_path("s1")
