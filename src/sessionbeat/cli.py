import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from sessionbeat import wire
from sessionbeat.board import Board
from sessionbeat.eventlog import read_events
from sessionbeat.events import (
    CardWritten,
    CheckRan,
    EventBase,
    GoalSet,
    PlanSet,
    StepsDone,
    StepStarted,
    TermDefined,
)

USAGE_EXIT = 2
NOT_STARTED_EXIT = 127
# `check` runs one program with no shell, so these would run in a child and record a lie.
SHELL_BUILTINS = ("cd", "export", "source", ".")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_E = TypeVar("_E", bound=EventBase)
NO_SESSION_MESSAGE = "no agent session found ({names} is not set)"


class Refusal(Exception):
    """A command the user can fix; reported on one line, exit code 2."""


def _log_path(session_id: str) -> Path:
    try:
        return wire.session_log_path(session_id)
    except ValueError as error:
        raise Refusal(str(error)) from error


def _load_board(session_id: str) -> Board:
    path = _log_path(session_id)
    # A session that has written nothing yet has no log file: zero goals, zero steps.
    events = read_events(path) if path.exists() else []
    return Board.from_events(session_id, events)


def _session_from_env() -> tuple[wire.AgentName, str] | None:
    for agent, variable in wire.SESSION_ENV.items():
        session_id = os.environ.get(variable)
        if session_id is not None:
            return agent, session_id
    return None


class AgentSession:
    """The session a writing command belongs to, found from the agent's environment."""

    def __init__(self, agent: wire.AgentName, session_id: str) -> None:
        self.agent = agent
        self.session_id = session_id

    @classmethod
    def from_env(cls) -> "AgentSession":
        found = _session_from_env()
        if found is None:
            names = ", ".join(wire.SESSION_ENV.values())
            raise Refusal(NO_SESSION_MESSAGE.format(names=names))
        return cls(*found)

    def board(self) -> Board:
        return _load_board(self.session_id)

    def write(self, event_type: type[_E], **fields: object) -> _E:
        """Build the event first so its validators enforce the limits, then append it."""
        try:
            event = event_type.model_validate(
                {"at": datetime.now(UTC), "agent": self.agent, **fields}
            )
        except ValidationError as error:
            raise Refusal(_describe(error)) from error
        stored = event.model_dump(exclude={"at", "agent"})
        kind = wire.Kind(stored.pop("kind"))
        wire.append_record(self.session_id, self.agent, kind, stored, event.at)
        return event


def _describe(error: ValidationError) -> str:
    lines = []
    for problem in error.errors():
        field = ".".join(str(part) for part in problem["loc"])
        value = problem["input"]
        size = f" (got {len(value)} characters)" if isinstance(value, str) else f" (got {value!r})"
        lines.append(f"{field}: {problem['msg']}{size}")
    return "\n".join(lines)


def _goal(args: argparse.Namespace) -> int:
    session = AgentSession.from_env()
    number = len(session.board().goals) + 1
    session.write(GoalSet, text=args.text)
    print(f"goal {number}")
    return 0


def _plan(args: argparse.Namespace) -> int:
    AgentSession.from_env().write(PlanSet, steps=args.steps)
    return 0


def _step(args: argparse.Namespace) -> int:
    session = AgentSession.from_env()
    if args.which == "done":
        session.write(StepsDone)
        return 0
    steps = len(session.board().steps)
    if not 1 <= args.which <= steps:
        raise Refusal(f"step {args.which} is past the end of the plan ({steps} steps)")
    session.write(StepStarted, number=args.which)
    return 0


def _check(args: argparse.Namespace) -> int:
    session = AgentSession.from_env()
    goals = len(session.board().goals)
    if not 1 <= args.goal <= goals:
        raise Refusal(f"goal {args.goal} does not exist ({goals} goals)")
    command: list[str] = args.command
    first = command[0]
    if first in SHELL_BUILTINS or ENV_ASSIGNMENT.match(first):
        raise Refusal(
            f'check cannot run "{first}": check runs one program with no shell, '
            "so shell syntax would record the wrong result"
        )
    try:
        returncode = subprocess.run(command).returncode
    except (FileNotFoundError, PermissionError) as error:
        print(f"sessionbeat: cannot start {first!r}: {error}", file=sys.stderr)
        return NOT_STARTED_EXIT
    session.write(CheckRan, goal=args.goal, argv=command, exit_code=returncode)
    # A negative code means the child died from a signal; report it the way a shell would.
    return 128 - returncode if returncode < 0 else returncode


def _term(args: argparse.Namespace) -> int:
    AgentSession.from_env().write(TermDefined, label=args.label, meaning=args.meaning)
    return 0


def _card(args: argparse.Namespace) -> int:
    AgentSession.from_env().write(CardWritten, before=args.before, after=args.after)
    return 0


def _step_argument(text: str) -> int | str:
    if text == "done":
        return text
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid step {text!r}: expected 'done' or a step number"
        ) from None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sessionbeat")
    commands = parser.add_subparsers(dest="command_name", required=True)

    goal = commands.add_parser("goal", help="name a goal; prints its number")
    goal.add_argument("text")
    goal.set_defaults(run=_goal)

    plan = commands.add_parser("plan", help="set the plan")
    plan.add_argument("steps", nargs="+", metavar="STEP")
    plan.set_defaults(run=_plan)

    step = commands.add_parser("step", help="start step N, or 'done' when all are finished")
    step.add_argument("which", type=_step_argument, metavar="N|done")
    step.set_defaults(run=_step)

    check = commands.add_parser("check", help="run a command as proof for goal N")
    check.add_argument("goal", type=int, metavar="N")
    check.usage = "sessionbeat check N -- CMD [ARG ...]"
    check.set_defaults(run=_check)

    term = commands.add_parser("term", help="define a word the agent uses")
    term.add_argument("label")
    term.add_argument("meaning")
    term.set_defaults(run=_term)

    card = commands.add_parser("card", help="write a before/after card")
    card.add_argument("--before", required=True)
    card.add_argument("--after", required=True)
    card.set_defaults(run=_card)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    command: list[str] = []
    # Everything after `--` belongs to the inner command, so argparse never sees its flags.
    if arguments[:1] == ["check"] and "--" in arguments:
        split = arguments.index("--")
        arguments, command = arguments[:split], arguments[split + 1 :]
    args = parser.parse_args(arguments)
    if args.command_name == "check":
        if not command:
            parser.error("check needs a command after '--': sessionbeat check N -- CMD [ARG ...]")
        args.command = command
    try:
        code: int = args.run(args)
    except Refusal as refusal:
        for line in str(refusal).splitlines():
            print(f"sessionbeat: {line}", file=sys.stderr)
        raise SystemExit(USAGE_EXIT) from None
    raise SystemExit(code)
