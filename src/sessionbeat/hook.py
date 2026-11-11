"""Hook entry point: one agent payload on stdin becomes at most one log line.

Standard library only: this runs on every tool call and must start fast.
"""

import json
import sys
from datetime import UTC, datetime

from sessionbeat.adapters import ADAPTERS, string_field
from sessionbeat.wire import AgentName, append_record


def main() -> None:
    at = datetime.now(UTC)
    allowed = ", ".join(a.value for a in AgentName)
    given = sys.argv[1] if len(sys.argv) > 1 else None
    if given not in set(AgentName):
        print(
            f"sessionbeat-hook: agent name {given!r} is not one of: {allowed}",
            file=sys.stderr,
        )
        sys.exit(1)
    agent = AgentName(given)
    payload = json.load(sys.stdin.buffer)
    if not isinstance(payload, dict):
        raise TypeError(f"Hook stdin must be a JSON object, got {type(payload).__name__}")
    fact = ADAPTERS[agent](payload)
    if fact is None:
        return
    kind, fields = fact
    append_record(string_field(payload, "session_id"), agent, kind, fields, at)


if __name__ == "__main__":
    main()
