# ADR 0001: A status board that hooks and the agent write together

- Status: accepted
- Date: 2026-11-10
- Supersedes: none

## Problem

A coding agent can work for hours and hundreds of tool calls. The person who
started the task then has to read the transcript, or ask the agent, to learn
where things stand. sessionbeat is a local page that answers that without
either.

## What the page must answer

Before the design, 96 of the author's own agent sessions (2026-10-07 to
2026-11-10, 1,489 short typed messages) were searched by keyword for moments
where the person had to ask for status. The five most common questions, by
share of sessions:

| Question | Share of sessions | Panel on the page |
|---|---|---|
| Is it done? Did it work? | 30% | Is it done? |
| What does this term or ID mean? | 26% to 35% | Words the agent uses |
| Does it need me? What next? | 24% | Your turn |
| Where are we? | 21% | Where are we? |
| What did we do? | 14% to 21% | What changed? |

"Is it stuck?" and "what are the subagents doing?" almost never appeared, so
the page has no live activity feed and no subagent panel.

Caveat: keyword matching found a category for only 246 of the 1,489 messages,
from one person over five weeks. The ranking is a guide, not a measurement.

## Decision

```
 Claude Code ─┐  hooks                        ┌─► Your turn
 Codex CLI   ─┴─► adapter ──┐                 ├─► Is it done?   (goal + check)
                            ▼                 ├─► Where are we? (plan steps)
                   one JSONL log per ─► Board ─► local page
                   session            ▲       ├─► What changed? (before/after)
 the agent ── short commands ─────────┘       └─► Words the agent uses
```

1. **Hooks record facts; the agent records meaning.** Hooks cost no tokens and
   capture what can be observed: a turn ended, a permission is pending, a file
   changed. Only the agent knows the goal, the plan, what its labels mean and
   how behaviour changed, so it writes those with short shell commands.
2. **Capture: the hook appends one small line to a log file.** No server has
   to be running to record, and the log can be replayed.
3. **State: one append-only JSONL log per session**, at
   `~/.sessionbeat/sessions/<session id>.jsonl`. A `Board` object is built only
   by applying the events in order. Nothing else holds state.
4. **The agent writes through shell commands**: `goal`, `plan`, `step`,
   `check`, `term`, `card`. Text length is capped, which caps token cost.
5. **`check <goal> -- <command>` runs the proof command itself** and records
   the real exit code. The board shows a goal as proven only from that.
6. **First release supports Claude Code and Codex CLI**, each through one
   adapter function that turns a hook payload into a fact.
7. **The hook entry point uses only the Python standard library.** Pydantic
   validates events where the board reads the log.
8. **Display: a local web page** served on `127.0.0.1`, with a `Host` header
   check and a token in the URL. Agent-written text is rendered as text.

### Rules that follow from the decision

**`check` must not become a way around the user's permissions.**

- Install adds one allow rule per writing command: `goal`, `plan`, `step`,
  `term` and `card`. It adds none for `check`, so the agent's normal
  permission prompt shows the full command. A blanket `Bash(sessionbeat *)`
  rule would let `sessionbeat check 1 -- <any command>` run unprompted, which
  the Claude Code permissions page warns about for commands that run their
  arguments.
- `check` starts the command with no shell and refuses `cd`, `export`,
  `source`, `.` and `NAME=value` as the command name. Otherwise
  `check 1 -- cd x && pytest` would record the exit code of `cd` alone.
- `check` passes output straight through, exits with the command's own exit
  code, and writes its event only when the command finishes. The board shows
  the exact command next to the result.

**"Your turn" is set and cleared by direct events only.**

- Every `Stop` sets it, with the agent's last message. If background tasks are
  still running, the banner names them. A missing task list means unknown, not
  zero.
- `StopFailure` sets it, with the error.
- `PermissionRequest` sets a pending request keyed by tool name and input. A
  later `PostToolUse` or `PostToolUseFailure` with the same pair removes it.
- `UserPromptSubmit` clears everything and shows "agent working". It also
  fires for scheduled tasks and subagent reports, and the agent is working
  again in those cases too.

**Steps.** `plan` replaces the step list and resets the current step. `step N`
moves the marker, `step done` finishes the last one, and a number past the end
is an error.

**Reminder.** One nudge per session, sent with a tool result when files have
changed and the board has no goal. That hook is synchronous and holds a file
lock while it reads and writes, because hooks for parallel tool calls run at
the same time.

## Alternatives and why they lost

| Alternative | What it gains | Why not |
|---|---|---|
| Hook posts to a local server | No process start per hook | Events are lost when the server is down; replay needs a second log |
| No hooks; read the agent's transcript files | No install step | Formats are private and differ per agent; no "waiting" signal |
| Agent writes through an MCP tool | Typed input | Tool definitions cost tokens in every session; setup per agent |
| A pane inside Claude Code ("mods") | Sits beside the transcript | Only Claude Code has it, which breaks the multi-agent goal |
| Read plan steps from Claude Code's task tools | No command per step | Off by default on current models; Claude Code only; no "in progress" signal. Kept as a later candidate |
| Match a claimed command against recorded shell commands | No extra command | `pytest \| tail` exits 0 when tests fail, so it can show a false pass |
| Key the log by workspace folder | Simple to explain | The hook `cwd` follows the agent's `cd`; two sessions in one repo would share a board |

## Evidence

Checked against the official pages on 2026-11-10:

- Claude Code hooks (<https://code.claude.com/docs/en/hooks>): `Stop` carries
  `last_assistant_message` and `background_tasks`; `PostToolUse` fires only
  after a tool succeeds and `PostToolUseFailure` after it fails; `Stop`
  `additionalContext` continues the conversation; an `Edit|Write` hook does
  not fire when a shell command rewrites a file.
- Claude Code env vars (<https://code.claude.com/docs/en/env-vars>):
  `CLAUDE_CODE_SESSION_ID` is set in shell and hook subprocesses and matches
  the hook `session_id`. Also observed in a live session.
- Claude Code tools reference
  (<https://code.claude.com/docs/en/tools-reference>): the task tools are on
  by default only on older models.
- Claude Code permissions (<https://code.claude.com/docs/en/permissions>): a
  rule for a command that runs its arguments "matches whatever comes after";
  `PermissionRequest` carries the tool name and input but no tool-use id.
- Codex hooks (<https://learn.chatgpt.com/docs/hooks>): same core fields
  (`session_id`, `hook_event_name`, `tool_name`, `tool_input`); file edits
  arrive as `apply_patch`; no `StopFailure`; new or changed hooks are skipped
  until trusted.
- Hook cost: a standard-library-only Python process that reads JSON and
  appends one line took 16.2 ms median and 17.4 ms p95 (40 runs, Python
  3.14.8, one Apple laptop). A reviewer measured about 60 ms with a Pydantic
  import, which is why the hook does not import it.
- Prior art, source read on 2026-11-10: `claude-code-hooks-multi-agent-observability`,
  `Claude-Code-Agent-Monitor`, `claude-agent-panel`, `agentsview` and
  `vibe-kanban`. All show automatically captured activity. None shows text
  that the working agent wrote for the person.

## Not verified yet

These must be tested on a real Codex session before the Codex adapter is built:

- whether Codex sets `CODEX_THREAD_ID` (or any session id) for shell commands
- whether the Codex sandbox lets a command write under the home folder

And on a real Claude Code session:

- whether choosing "don't ask again" on a `check` prompt saves a broad
  `sessionbeat check` rule. If it does, the README must warn against it.

## Known limits

- The board is only as true as the agent keeps it. This is the main risk and
  is measured (see below), not assumed.
- A file changed by a shell command is not seen, so the "files changed since
  the check" flag can miss it.
- If the agent runs its tests directly and not through `check`, the goal shows
  "no check". The compliance test counts how often that happens.
- When the user interrupts a turn, no `Stop` event fires, so the board keeps
  showing "agent working" until the next event.
- A check that outlives the agent's command timeout is moved to the
  background and its result arrives late.
- `/clear` and forks create a new session id and therefore a new board.
- The agent can write to the log file. The board is a view, not an audit record.
- No Windows support in the first release.

## How we will know it works

| Test | Pass |
|---|---|
| Glance: answers written from the transcript first; a person who did not run the session sees a replay paused at a random point for 10 seconds | 4 of 5 questions right |
| Hook cost over 200 runs | p95 under 50 ms |
| Agent cost: instructions text plus requests that only ran a `sessionbeat` command | under 2% of session tokens |
| Compliance: board compared with the transcript at the end of 5 real sessions | 4 of 5 boards are true |
| Install from the README in a new user account | page open within 5 minutes |
