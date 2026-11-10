from pathlib import Path

from pydantic import ValidationError

from sessionbeat.events import EVENT_ADAPTER, Event


def read_events(path: Path) -> list[Event]:
    lines = path.read_bytes().split(b"\n")
    # The piece after the last newline is empty for a clean file; otherwise it is a torn write
    # from a killed writer. Either way it is not a complete record.
    lines.pop()
    events: list[Event] = []
    for number, line in enumerate(lines, start=1):
        try:
            events.append(EVENT_ADAPTER.validate_json(line))
        except ValidationError as error:
            raise ValueError(f"Invalid event in {path} at line {number}: {error}") from error
    return events
