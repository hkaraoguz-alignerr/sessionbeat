"""Agent payload adapters. Standard library only: the hook imports this and must start fast."""

from collections.abc import Callable

from sessionbeat.wire import AgentName, Kind, cut, input_key

Fact = tuple[Kind, dict[str, object]]

FILE_EDIT_TOOLS = frozenset({"Edit", "Write"})


def _storable(value: str) -> str:
    # A lone surrogate (half an emoji) cannot be stored as UTF-8 and would break reading the log.
    return value.encode("utf-8", "surrogatepass").decode("utf-8", "replace")


def string_field(container: dict[str, object], key: str) -> str:
    value = container[key]
    if not isinstance(value, str):
        raise TypeError(f"Payload key {key!r} must be a string, got {type(value).__name__}")
    return _storable(value)


def _dict(container: dict[str, object], key: str) -> dict[str, object]:
    value = container[key]
    if not isinstance(value, dict):
        raise TypeError(f"Payload key {key!r} must be an object, got {type(value).__name__}")
    return {str(k): v for k, v in value.items()}


def _background(payload: dict[str, object]) -> list[str] | None:
    if "background_tasks" not in payload:
        return None
    tasks = payload["background_tasks"]
    if not isinstance(tasks, list):
        raise TypeError(
            f"Payload key 'background_tasks' must be a list, got {type(tasks).__name__}"
        )
    descriptions: list[str] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise TypeError(
                f"Payload key 'background_tasks'[{index}] must be an object, "
                f"got {type(task).__name__}"
            )
        description = task["description"]
        if not isinstance(description, str):
            raise TypeError(
                f"Payload key 'background_tasks'[{index}].description must be a string, "
                f"got {type(description).__name__}"
            )
        descriptions.append(_storable(description))
    return descriptions


def claude_code_fact(payload: dict[str, object]) -> Fact | None:
    event = string_field(payload, "hook_event_name")
    if event == "SessionStart":
        return Kind.SESSION_STARTED, {
            "cwd": string_field(payload, "cwd"),
            "source": string_field(payload, "source"),
        }
    if event == "Stop":
        last_message, truncated = cut(string_field(payload, "last_assistant_message"))
        return Kind.TURN_ENDED, {
            "last_message": last_message,
            "truncated": truncated,
            "background": _background(payload),
        }
    if event == "StopFailure":
        message = ""
        if "last_assistant_message" in payload:
            message, _ = cut(string_field(payload, "last_assistant_message"))
        return Kind.TURN_FAILED, {"error": string_field(payload, "error"), "message": message}
    if event == "PermissionRequest":
        return Kind.PERMISSION_ASKED, {
            "tool": string_field(payload, "tool_name"),
            "input_key": input_key(_dict(payload, "tool_input")),
        }
    if event in ("PostToolUse", "PostToolUseFailure"):
        tool = string_field(payload, "tool_name")
        tool_input = _dict(payload, "tool_input")
        path = None
        if event == "PostToolUse" and tool in FILE_EDIT_TOOLS:
            path = string_field(tool_input, "file_path")
        return Kind.TOOL_FINISHED, {"tool": tool, "input_key": input_key(tool_input), "path": path}
    if event == "UserPromptSubmit":
        return Kind.USER_ANSWERED, {}
    return None


ADAPTERS: dict[AgentName, Callable[[dict[str, object]], Fact | None]] = {
    AgentName.CLAUDE_CODE: claude_code_fact,
}
