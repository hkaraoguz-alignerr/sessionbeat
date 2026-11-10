import sys
from pathlib import Path

import pytest

from sessionbeat import cli, wire
from sessionbeat.board import Board
from sessionbeat.eventlog import read_events


@pytest.fixture(autouse=True)
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSIONBEAT_HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "demo")


def load_board() -> Board:
    return Board.from_events("demo", read_events(wire.session_log_path("demo")))


def run_check(goal: str, exit_code: int) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["check", goal, "--", sys.executable, "-c", f"raise SystemExit({exit_code})"])
    assert raised.value.code == exit_code


def run(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 0


def test_agent_session_flow(capsys: pytest.CaptureFixture[str]) -> None:
    run(["goal", "Tests pass"])
    assert capsys.readouterr().out == "goal 1\n"
    run(["plan", "Write it", "Test it", "Ship it"])
    run(["step", "2"])
    run_check("1", 0)
    run_check("1", 3)
    run(["term", "D6", "the sixth decision"])
    run(["card", "--before", "no CLI", "--after", "a CLI"])

    board = load_board()
    check = board.goals[0].check
    assert check is not None and check.exit_code == 3
    assert board.current_step == 2
    assert board.terms == {"D6": "the sixth decision"}
    assert len(board.cards) == 1


@pytest.mark.parametrize(
    ("argv", "env_set"),
    [
        (["check", "1", "--", "cd", "x"], True),
        (["check", "1", "--", "FOO=1", "pytest"], True),
        (["check", "9", "--", "true"], True),
        (["step", "9"], True),
        (["goal", "x" * 121], True),
        (["goal", "fine"], False),
    ],
)
def test_refusals_exit_2_and_write_nothing(
    argv: list[str], env_set: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(["goal", "Tests pass"])
    before = wire.session_log_path("demo").read_bytes()
    if not env_set:
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 2
    assert wire.session_log_path("demo").read_bytes() == before
