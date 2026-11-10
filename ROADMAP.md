# Roadmap

The design is in [ADR 0001](docs/adr/0001-status-board-design.md). Items are
in build order. Each one ships with its tests.

## First release

1. **Project setup**: `uv` project, `ruff` and `mypy` in pre-commit.
2. **Codex unknowns**: on a real Codex session, confirm the session id
   variable for shell commands and that a command can write under the home
   folder. Record the result in the ADR.
3. **Event model and board**: the event types, the per-session log reader, and
   `Board.apply`.
4. **Hook entry point and Claude Code adapter**: standard library only; measure
   the hook cost over 200 runs.
5. **Agent commands**: `goal`, `plan`, `step`, `check`, `term`, `card`, with
   length limits.
6. **Counters**: hook cost, agent cost and reminder count, so the acceptance
   tests can be run before the page is polished.
7. **Page and server**: the five panels, live updates, the session list, the
   `Host` check and the URL token.
8. **Replay**: rebuild a board from a log up to a chosen point.
9. **Install, uninstall and doctor** for Claude Code.
10. **Codex adapter and install**, including the hook trust step.
11. **Reminder**: one nudge when files have changed and the board has no goal.
12. **Acceptance tests** from the ADR, with the results written up.

## Later candidates

- Read plan steps from Claude Code's task tools instead of the `step` command.
- Adapters for Cursor, Copilot CLI and OpenCode.
- See file changes made by shell commands.
- Join the boards of one task across `/clear` and forked sessions.
- Windows support.
