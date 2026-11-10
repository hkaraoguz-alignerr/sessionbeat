import re
import shlex
from datetime import datetime

from sessionbeat.board import Board, TurnEndedState
from sessionbeat.wire import CONTROL_CHAR_CLASS

EMPTY = "-"
CONTROL_CHAR = re.compile(f"[{CONTROL_CHAR_CLASS}]")


def _one_line(text: str) -> str:
    """Keep a single-line value on its line: a raw newline could print a fake heading."""
    return text.replace("\n", "\\n")


def _clock(moment: datetime) -> str:
    return moment.astimezone().strftime("%H:%M")


def _your_turn(board: Board) -> list[str]:
    lines: list[str] = []
    turn = board.turn
    if turn is None:
        lines.append("agent working")
    elif isinstance(turn, TurnEndedState):
        lines.append(f"turn ended, since {_clock(turn.since)}")
        lines.extend(turn.text.splitlines())
        if turn.background is None:
            lines.append("background tasks unknown")
        elif turn.background:
            lines.append(f"background tasks: {', '.join(map(_one_line, turn.background))}")
    else:
        lines.append(f"turn failed, since {_clock(turn.since)}: {_one_line(turn.error)}")
        lines.extend(turn.message.splitlines())
    for (tool, _), asked in board.pending_permissions.items():
        lines.append(f"waiting for permission: {_one_line(tool)}, since {_clock(asked)}")
    return lines


def _is_it_done(board: Board) -> list[str]:
    lines: list[str] = []
    for number, goal in enumerate(board.goals, start=1):
        check = goal.check
        if check is None:
            lines.append(f"○ {number}. {goal.text} · no check")
        elif check.passed:
            stale = " · files changed since" if board.check_is_stale(goal) else ""
            lines.append(f"✓ {number}. {goal.text} · check passed {_clock(check.at)}{stale}")
        else:
            lines.append(f"✗ {number}. {goal.text} · check failed {_clock(check.at)}")
        if check is not None:
            lines.append(f"    $ {_one_line(shlex.join(check.argv))}")
    return lines


def _where_are_we(board: Board) -> list[str]:
    lines: list[str] = []
    for number, step in enumerate(board.steps, start=1):
        mark = "✓" if step.done else "▶" if number == board.current_step else "○"
        lines.append(f"{mark} {number}. {step.text}")
    if board.steps or board.edited_files:
        count = len(board.edited_files)
        lines.append(f"{count} file{'' if count == 1 else 's'} changed")
    return lines


def _what_changed(board: Board) -> list[str]:
    lines: list[str] = []
    for card in board.cards:
        if lines:
            lines.append("")
        lines.append(f"before: {card.before}")
        lines.append(f"after:  {card.after}")
    return lines


def _words(board: Board) -> list[str]:
    return [f"{label}: {meaning}" for label, meaning in board.terms.items()]


def _escape_controls(text: str) -> str:
    def show(match: re.Match[str]) -> str:
        char = match.group()
        return char if char == "\n" else f"\\x{ord(char):02x}"

    return CONTROL_CHAR.sub(show, text)


def render_text(board: Board) -> str:
    sections = [
        ("Your turn", _your_turn(board)),
        ("Is it done?", _is_it_done(board)),
        ("Where are we?", _where_are_we(board)),
        ("What changed?", _what_changed(board)),
        ("Words the agent uses", _words(board)),
    ]
    blocks = []
    for heading, lines in sections:
        body = [f"  {line}" if line else "" for line in lines] or [f"  {EMPTY}"]
        blocks.append("\n".join([heading, *body]))
    return _escape_controls("\n\n".join(blocks))
