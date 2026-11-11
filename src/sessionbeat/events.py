from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
)

from sessionbeat.wire import (
    CARD_TEXT_MAX,
    CONTROL_CHAR_CLASS,
    LABEL_MAX,
    PLAN_STEPS_MAX,
    SHORT_TEXT_MAX,
    AgentName,
    Kind,
)

NO_CONTROL_CHARS = f"^[^{CONTROL_CHAR_CLASS}]*$"

ShortText = Annotated[
    str, StringConstraints(min_length=1, max_length=SHORT_TEXT_MAX, pattern=NO_CONTROL_CHARS)
]
CardText = Annotated[
    str, StringConstraints(min_length=1, max_length=CARD_TEXT_MAX, pattern=NO_CONTROL_CHARS)
]
Label = Annotated[
    str, StringConstraints(min_length=1, max_length=LABEL_MAX, pattern=NO_CONTROL_CHARS)
]


class EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    at: AwareDatetime
    agent: AgentName


class SessionStarted(EventBase):
    kind: Literal[Kind.SESSION_STARTED] = Kind.SESSION_STARTED
    cwd: str
    source: str


class TurnEnded(EventBase):
    kind: Literal[Kind.TURN_ENDED] = Kind.TURN_ENDED
    last_message: str
    truncated: bool
    background: list[str] | None


class TurnFailed(EventBase):
    kind: Literal[Kind.TURN_FAILED] = Kind.TURN_FAILED
    error: str
    message: str


class PermissionAsked(EventBase):
    kind: Literal[Kind.PERMISSION_ASKED] = Kind.PERMISSION_ASKED
    tool: str
    input_key: str


class ToolFinished(EventBase):
    kind: Literal[Kind.TOOL_FINISHED] = Kind.TOOL_FINISHED
    tool: str
    input_key: str
    path: str | None


class UserAnswered(EventBase):
    kind: Literal[Kind.USER_ANSWERED] = Kind.USER_ANSWERED


class GoalSet(EventBase):
    kind: Literal[Kind.GOAL_SET] = Kind.GOAL_SET
    text: ShortText


class PlanSet(EventBase):
    kind: Literal[Kind.PLAN_SET] = Kind.PLAN_SET
    steps: Annotated[list[ShortText], Field(min_length=1, max_length=PLAN_STEPS_MAX)]


class StepStarted(EventBase):
    kind: Literal[Kind.STEP_STARTED] = Kind.STEP_STARTED
    number: Annotated[int, Field(ge=1)]


class StepsDone(EventBase):
    kind: Literal[Kind.STEPS_DONE] = Kind.STEPS_DONE


class CheckRan(EventBase):
    kind: Literal[Kind.CHECK_RAN] = Kind.CHECK_RAN
    goal: Annotated[int, Field(ge=1)]
    argv: Annotated[list[str], Field(min_length=1)]
    exit_code: int


class TermDefined(EventBase):
    kind: Literal[Kind.TERM_DEFINED] = Kind.TERM_DEFINED
    label: Label
    meaning: ShortText


class CardWritten(EventBase):
    kind: Literal[Kind.CARD_WRITTEN] = Kind.CARD_WRITTEN
    before: CardText
    after: CardText


Event = Annotated[
    SessionStarted
    | TurnEnded
    | TurnFailed
    | PermissionAsked
    | ToolFinished
    | UserAnswered
    | GoalSet
    | PlanSet
    | StepStarted
    | StepsDone
    | CheckRan
    | TermDefined
    | CardWritten,
    Field(discriminator="kind"),
]

EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)
