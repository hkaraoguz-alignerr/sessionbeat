"""Agent payload adapters. Standard library only: the hook imports this and must start fast."""

from collections.abc import Callable

from sessionbeat.wire import AgentName, Kind, cut, input_key

Fact = tuple[Kind, dict[str, object]]

FILE_EDIT_TOOLS = frozenset({"Edit", "Write"})


def _str(container: dict[str, object], key: str) -> str:
    value = container[key]
    if not isinstance(value, str):
        raise TypeError(f"Payload key {key!r} must be a string, got {type(value).__name__}")
    return value


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
        descriptions.append(description)
    return descriptions


def claude_code_fact(payload: dict[str, object]) -> Fact | None:
    event = _str(payload, "hook_event_name")
    if event == "SessionStart":
        return Kind.SESSION_STARTED, {
            "cwd": _str(payload, "cwd"),
            "source": _str(payload, "source"),
        }
    if event == "Stop":
        last_message, truncated = cut(_str(payload, "last_assistant_message"))
        return Kind.TURN_ENDED, {
            "last_message": last_message,
            "truncated": truncated,
            "background": _background(payload),
        }
    if event == "StopFailure":
        message = ""
        if "last_assistant_message" in payload:
            message, _ = cut(_str(payload, "last_assistant_message"))
        return Kind.TURN_FAILED, {"error": _str(payload, "error"), "message": message}
    if event == "PermissionRequest":
        return Kind.PERMISSION_ASKED, {
            "tool": _str(payload, "tool_name"),
            "input_key": input_key(_dict(payload, "tool_input")),
        }
    if event in ("PostToolUse", "PostToolUseFailure"):
        tool = _str(payload, "tool_name")
        tool_input = _dict(payload, "tool_input")
        path = None
        if event == "PostToolUse" and tool in FILE_EDIT_TOOLS:
            path = _str(tool_input, "file_path")
        return Kind.TOOL_FINISHED, {"tool": tool, "input_key": input_key(tool_input), "path": path}
    if event == "UserPromptSubmit":
        return Kind.USER_ANSWERED, {}
    return None


ADAPTERS: dict[AgentName, Callable[[dict[str, object]], Fact | None]] = {
    AgentName.CLAUDE_CODE: claude_code_fact,
}
