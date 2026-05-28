# ChatBoks

Local multi-agent coding orchestration for Claude, Codex, and other AI agents via a shared relay, CodeGraph context, and human approval.

ChatBoks is a human-supervised multi-agent relay for coding projects. Claude, Codex, and eventually Antigravity collaborate through a shared `chatboks.md` stream while the orchestrator maintains `.chatboks/state.json` for machine-readable state.

## Files

- `orchestrator.py`: main terminal process and approval gates
- `config.yaml`: projects, agent roles, token limits, and CodeGraph settings
- `router.py`: chooses the primary agent and wrapper instances
- `agents/`: CLI wrappers for Claude, Codex, and Antigravity
- `context/builder.py`: packages CodeGraph, recent ChatBoks history, and active task
- `context/summarizer.py`: deterministic fallback summary for token resets
- `ui/stream.py`: Rich terminal UI
- `hooks/post-commit`: optional async handoff hook

## Protocol

`chatboks.md` is human-readable. Agent and system messages use tags:

- `[SYSTEM]`
- `[CLAUDE]`
- `[CODEX]`
- `[ANTIGRAV]`
- `[YOU]`

The orchestrator only acts automatically on control lines:

- `>>> PROPOSAL`: plan ready, needs user approval
- `>>> QUESTION`: agent needs user input
- `>>> HANDOFF`: agent passes work to the next agent
- `>>> SKIP`: agent intentionally passes because it has nothing materially different to add
- `>>> SUMMARY_CHECKPOINT`: transcript compaction boundary for future context loads
- `>>> TASK_COMPLETE`: agent finished the work
- `>>> BLOCKED`: agent cannot proceed

`state.json` is written under each project at `.chatboks/state.json`.

## Run

```bash
pip install -r requirements.txt
python orchestrator.py taskfish
```

Use `--watch` to watch `chatboks.md` for handoffs, or `--trigger=commit` from the post-commit hook.

Run diagnostics with:

```bash
python doctor.py taskfish
```

## CodeGraph

The context builder expects CodeGraph as SQLite, not JSON. It looks for:

- `codegraph.db`
- `.codegraph/codegraph.db`
- `.codegraph/index.db`

It queries `files`, `nodes`, `edges`, and optional `project_metadata` tables when present.
