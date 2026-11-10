# sessionbeat

A local status board that shows where a coding agent's task stands, so you do
not have to read the transcript or ask.

> **Status: design accepted, build starting.** There is nothing to install yet.
> The design is in [ADR 0001](docs/adr/0001-status-board-design.md) and the
> build order is in the [roadmap](ROADMAP.md).

## What it will show

One page per agent session, with a panel for each question people ask
mid-task:

| Panel | Answers | Written by |
|---|---|---|
| Your turn | Does it need me? | hooks |
| Is it done? | Did it work? | the agent names the goal; `sessionbeat check` runs the proof |
| Where are we? | Which step is it on? | the agent |
| What changed? | How does it behave now, compared with before? | the agent |
| Words the agent uses | What do "D6" and "T1" mean? | the agent |

## How it works

```
 Claude Code ─┐  hooks (no tokens)
 Codex CLI   ─┴─► adapter ──► one JSONL log per session ──► Board ──► local page
 the agent ── short shell commands ──────────▲
```

- **Hooks record facts**: a turn ended, a permission is pending, a file changed.
- **The agent records meaning** with short commands such as
  `sessionbeat goal 'Session survives 30 min idle'` and
  `sessionbeat check 1 -- pytest tests/auth`.
- **The log is the only state.** The page is rebuilt from it, so a session can
  be replayed.

## Who it is for

People who hand long tasks to a coding agent and want to see where things
stand at a glance. The first release targets Claude Code and Codex CLI on
macOS and Linux.

## Built with

Python 3.11+, [uv](https://docs.astral.sh/uv/), Pydantic, and a plain HTML page
with no build step.

## License

[MIT](LICENSE)
