from collections.abc import Iterable
from datetime import datetime
from typing import assert_never

from pydantic import BaseModel, ConfigDict

from sessionbeat.events import (
    CardWritten,
    CheckRan,
    Event,
    GoalSet,
    PermissionAsked,
    PlanSet,
    SessionStarted,
    StepsDone,
    StepStarted,
    TermDefined,
    ToolFinished,
    TurnEnded,
    TurnFailed,
    UserAnswered,
)
from sessionbeat.wire import AgentName


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Check(_Frozen):
    at: datetime
    argv: list[str]
    exit_code: int

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


class Goal(_Frozen):
    text: str
    check: Check | None


class Step(_Frozen):
    text: str
    done: bool


class Card(_Frozen):
    before: str
    after: str


class TurnEndedState(_Frozen):
    since: datetime
    text: str
    truncated: bool
    background: list[str] | None


class TurnFailedState(_Frozen):
    since: datetime
    error: str
    message: str


class Board(BaseModel):
    """Everything one session's page renders. Built only by applying events in order."""

    session_id: str
    agent: AgentName | None = None
    cwd: str | None = None
    turn: TurnEndedState | TurnFailedState | None = None
    pending_permissions: dict[tuple[str, str], datetime] = {}
    goals: list[Goal] = []
    steps: list[Step] = []
    current_step: int | None = None
    terms: dict[str, str] = {}
    cards: list[Card] = []
    edited_files: set[str] = set()
    last_edit_at: datetime | None = None

    @classmethod
    def from_events(cls, session_id: str, events: Iterable[Event]) -> "Board":
        board = cls(session_id=session_id)
        for event in events:
            board.apply(event)
        return board

    def apply(self, event: Event) -> None:
        match event:
            case SessionStarted():
                self.cwd = event.cwd
                self.agent = event.agent
            case TurnEnded():
                self.turn = TurnEndedState(
                    since=event.at,
                    text=event.last_message,
                    truncated=event.truncated,
                    background=event.background,
                )
                self.pending_permissions.clear()
            case TurnFailed():
                self.turn = TurnFailedState(
                    since=event.at, error=event.error, message=event.message
                )
                self.pending_permissions.clear()
            case UserAnswered():
                self.turn = None
                self.pending_permissions.clear()
            case PermissionAsked():
                self.pending_permissions[(event.tool, event.input_key)] = event.at
            case ToolFinished():
                self.pending_permissions.pop((event.tool, event.input_key), None)
                if event.path is not None:
                    self.edited_files.add(event.path)
                    self.last_edit_at = event.at
            case GoalSet():
                self.goals.append(Goal(text=event.text, check=None))
            case CheckRan():
                if not 1 <= event.goal <= len(self.goals):
                    raise ValueError(
                        f"check_ran refers to goal {event.goal} but the board has "
                        f"{len(self.goals)} goals"
                    )
                goal = self.goals[event.goal - 1]
                check = Check(at=event.at, argv=event.argv, exit_code=event.exit_code)
                self.goals[event.goal - 1] = Goal(text=goal.text, check=check)
            case PlanSet():
                self.steps = [Step(text=text, done=False) for text in event.steps]
                self.current_step = None
            case StepStarted():
                if not 1 <= event.number <= len(self.steps):
                    raise ValueError(
                        f"step {event.number} is past the end of the plan ({len(self.steps)} steps)"
                    )
                self.steps = [
                    Step(text=step.text, done=index < event.number)
                    for index, step in enumerate(self.steps, start=1)
                ]
                self.current_step = event.number
            case StepsDone():
                self.steps = [Step(text=step.text, done=True) for step in self.steps]
                self.current_step = None
            case TermDefined():
                self.terms[event.label] = event.meaning
            case CardWritten():
                self.cards.append(Card(before=event.before, after=event.after))
            case _:
                assert_never(event)

    def check_is_stale(self, goal: Goal) -> bool:
        return (
            goal.check is not None
            and goal.check.passed
            and self.last_edit_at is not None
            and self.last_edit_at > goal.check.at
        )

    @property
    def needs_user(self) -> bool:
        return self.turn is not None or bool(self.pending_permissions)
