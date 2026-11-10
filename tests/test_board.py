from datetime import UTC, datetime, timedelta

import pytest

from sessionbeat.board import Board
from sessionbeat.events import EVENT_ADAPTER, Event
from sessionbeat.wire import AgentName, Kind

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def ev(minute: int, kind: Kind, **fields: object) -> Event:
    return EVENT_ADAPTER.validate_python(
        {
            "at": T0 + timedelta(minutes=minute),
            "agent": AgentName.CLAUDE_CODE,
            "kind": kind,
            **fields,
        }
    )


def test_session_scenario() -> None:
    board = Board(session_id="s1")
    board.apply(ev(0, Kind.SESSION_STARTED, cwd="/repo", source="startup"))
    assert (board.cwd, board.agent) == ("/repo", AgentName.CLAUDE_CODE)
    assert not board.needs_user

    board.apply(ev(1, Kind.PERMISSION_ASKED, tool="Bash", input_key="k1"))
    assert board.needs_user
    board.apply(ev(2, Kind.TOOL_FINISHED, tool="Bash", input_key="k1", path=None))
    assert not board.needs_user
    assert board.last_edit_at is None

    board.apply(ev(3, Kind.GOAL_SET, text="tests pass"))
    goal = board.goals[0]
    assert goal.check is None
    board.apply(ev(4, Kind.CHECK_RAN, goal=1, argv=["pytest"], exit_code=0))
    goal = board.goals[0]
    assert goal.check is not None and goal.check.passed
    assert not board.check_is_stale(goal)
    board.apply(ev(5, Kind.TOOL_FINISHED, tool="Edit", input_key="k2", path="a.py"))
    assert board.edited_files == {"a.py"}
    assert board.check_is_stale(goal)
    board.apply(ev(6, Kind.CHECK_RAN, goal=1, argv=["pytest"], exit_code=1))
    failing = board.goals[0]
    assert failing.check is not None and not failing.check.passed
    assert not board.check_is_stale(failing)

    board.apply(ev(7, Kind.PLAN_SET, steps=["a", "b", "c"]))
    assert [s.done for s in board.steps] == [False, False, False]
    board.apply(ev(8, Kind.STEP_STARTED, number=2))
    assert [s.done for s in board.steps] == [True, False, False]
    assert board.current_step == 2
    board.apply(ev(9, Kind.STEPS_DONE))
    assert all(s.done for s in board.steps) and board.current_step is None

    board.apply(ev(10, Kind.TERM_DEFINED, label="board", meaning="the status page"))
    board.apply(ev(11, Kind.CARD_WRITTEN, before="old", after="new"))
    assert board.terms == {"board": "the status page"}
    assert [(c.before, c.after) for c in board.cards] == [("old", "new")]

    board.apply(ev(12, Kind.PERMISSION_ASKED, tool="Bash", input_key="k3"))
    board.apply(
        ev(13, Kind.TURN_ENDED, last_message="done", truncated=False, background=["server"])
    )
    assert board.needs_user and not board.pending_permissions
    assert board.turn is not None and board.turn.since == T0 + timedelta(minutes=13)
    board.apply(ev(14, Kind.USER_ANSWERED))
    assert board.turn is None and not board.needs_user

    with pytest.raises(ValueError, match="goal 3.*1 goals"):
        board.apply(ev(15, Kind.CHECK_RAN, goal=3, argv=["x"], exit_code=0))
    with pytest.raises(ValueError, match="step 4 is past the end of the plan"):
        board.apply(ev(16, Kind.STEP_STARTED, number=4))
