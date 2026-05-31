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

## Outcome Tracking

ChatBoks can track collaboration wins and failures as project-local JSONL telemetry in `.chatboks/outcomes.jsonl`.
These local slash commands do not call any agents or consume model tokens:

```text
/win codex missed_defect high "Caught the IPC pipe fallback issue."
/fail agent_zero bad_signal medium "Returned a bare QUESTION."
/outcome win claude better_architecture medium "Found the simpler protocol flow."
/wins
/failures
/outcomes
```

Use this to compare collaboration modes, agent combinations, and unique model contributions over time.

## Collaboration Modes

Modes are project-local prompt frames that tell agents how to collaborate. They do not route extra agents by themselves.

```text
/mode
/mode brainstorm
/mode bugsearch
/mode implement
/mode review
/mode diagnose
/mode default
```

- `brainstorm`: distinct ideas, options, tradeoffs, and risks.
- `bugsearch`: concrete defects, edge cases, regressions, and test gaps.
- `implement`: scoped patches, tests, and buildable changes.
- `review`: findings-first code review posture.
- `diagnose`: root cause and smallest useful probes.
- `default`: normal relay behavior.

## Run

```bash
pip install -r requirements.txt
python orchestrator.py taskfish
```

Use `--watch` to watch `chatboks.md` for handoffs, or `--trigger=commit` from the post-commit hook.

## Setup

Run the setup helper to check Node/npm, CodeGraph, and project indexes:

```bash
python install.py taskfish
```

The installer asks before installing anything. If Node.js is missing on Windows, it can offer to install Node.js LTS with `winget`. If CodeGraph is missing, it can offer to install `@colbymchenry/codegraph` globally with npm.

Run diagnostics with:

```bash
python doctor.py taskfish
```

By default, `doctor.py` avoids model-consuming calls. To test actual stdin piping through Claude/Codex, use:

```bash
python doctor.py taskfish --smoke-agents
```

Agent Zero is an optional local/bootstrap agent backed directly by Ollama. By default it calls `qwen2.5-coder:3b` through Ollama's local chat endpoint (`http://127.0.0.1:11434/api/chat`). It is configured but not added to project teams by default. To check Ollama/model availability and ask whether Agent Zero should join a project, run:

```bash
python install.py tinyguardian --agent-zero
```

You can also route to it directly without adding it to normal rounds:

```text
@zero check this project setup and recommend the next diagnostic command.
```

Make sure Ollama is running and the selected model exists locally, for example with `ollama pull qwen2.5-coder:3b`.

## CodeGraph (third-party integration)

ChatBoks integrates with [CodeGraph](https://github.com/colbymchenry/codegraph) by colbymchenry, a separate open-source tool that builds a semantic code knowledge graph from your project. Install it independently via:

    npx @colbymchenry/codegraph

The context builder integrates with [CodeGraph by colbymchenry](https://github.com/colbymchenry/codegraph), a separate MIT-licensed project. ChatBoks expects CodeGraph as SQLite, not JSON. It looks for:

- `codegraph.db`
- `.codegraph/codegraph.db`
- `.codegraph/index.db`

It queries `files`, `nodes`, `edges`, and optional `project_metadata` tables when present.

CodeGraph is an external dependency. For CodeGraph installation, indexing, parser, or database issues, use the CodeGraph project's support channels. ChatBoks support covers how ChatBoks consumes an existing CodeGraph SQLite database.

## License

ChatBoks is licensed under AGPL-3.0. CodeGraph is a separate MIT-licensed dependency.
