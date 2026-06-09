# ChatBoks

Local multi-agent coding orchestration for Claude, Codex, and other AI agents via a shared relay, CodeGraph context, and human approval.

ChatBoks is a human-supervised multi-agent relay for coding projects. Claude, Codex, and eventually Antigravity collaborate through a shared `chatboks.md` stream while the orchestrator maintains `.chatboks/state.json` for machine-readable state.

## Early Development Notice

ChatBoks is still in early development. It is an experimental local orchestration tool, not a hardened production
platform. If you choose to run it, automate with it, or expose any companion tooling around it, you do so at your own
risk and under your own responsibility.

This matters most for anything that can affect your real machine state, including agent-triggered edits, shell access,
git operations, hooks, and any remote access or mobile-control path. Review the code, keep the trust boundary narrow,
and do not expose local control surfaces to untrusted networks or users.

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

When you want help phrasing likely outcome entries from recent work, ask Agent Zero for suggestions:

```text
/suggest-outcome
/suggest-outcome codex
```

This is advisory only. Agent Zero suggests candidate `/win` or `/fail` lines, but nothing is written to
`.chatboks/outcomes.jsonl` until you run a manual outcome command yourself.

## Collaboration Modes

Modes are project-local prompt frames that tell agents how to collaborate. They can also apply a lightweight routing
strategy when the project config opts in.

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

ChatBoks supports separate lane order and routing strategy knobs per mode:

```yaml
projects:
  chatboks:
    mode_strategies:
      implement: solo_codex
      review: solo_claude
      diagnose: solo_claude
      bugsearch: full_round
      brainstorm: full_round
```

- `solo_codex`: route that mode's requests to Codex only unless an explicit `@agent` tag or a stronger lightweight
  Agent Zero route applies first.
- `solo_claude`: same idea, but Claude-first.
- `full_round`: keep the configured collaboration lane for that mode.

## Context Modes

Context modes control how much project context each agent receives. New sessions default to `lean` to reduce token burn.

```text
/context
/context lean
/context normal
/context full
```

- `lean`: active task, round state, agent status, last three transcript turns, compact outcomes, and CodeGraph status only.
- `normal`: current broad context behavior.
- `full`: maximum broad CodeGraph/file/symbol context for intentionally deep analysis.

Lean mode avoids broad CodeGraph dumps unless the user explicitly asks for code context.

## Native Skills

Native skills are markdown workflow cards in `skills/`. They document repeatable ChatBoks workflows without changing
agent routing. Modes still decide prompt framing, project config still decides which agents run, and skills remain
human/auditable guidance until explicitly wired into a mode.

```text
/skills
/skills implement
/skills bugsearch
```

Each skill uses the same schema: context priming, workflow steps, quality gate, and escalation triggers. See
`skills/README.md` for the schema and `skills/implement.md` / `skills/bugsearch.md` for reference skills.

## Agent Availability

When a model hits a provider limit or should be kept out of the next few rounds, mark it locally with `/agent`.
These commands do not call any agents or consume model tokens.

```text
/agent
/agent claude exhausted 50m
/agent claude available
/agent codex low
/agent agent_zero blocked "Ollama is offline"
```

Availability is stored per project in `.chatboks/agent_status.json` and included in round context. Normal multi-agent
rounds skip exhausted or blocked agents and use configured fallbacks when possible. Explicit routes such as `@claude`
do not silently substitute another model; ChatBoks tells you the target is unavailable so you can decide what to do.

Normal rounds use the configured default project team and exclude `direct_agents` such as Agent Zero. Use direct tags
like `@zero` when you want the local/bootstrap model specifically. Use `@all ...` to opt into the full configured
non-direct project team for one prompt. Local/direct agents can fill a main seat only when explicitly marked with
`can_fill_main_seat: true` and selected as a fallback for an exhausted agent.

## Routing Intelligence

ChatBoks can optionally use a small first-pass classifier before a normal round starts. This keeps explicit `@agent`
routes unchanged while letting cheap/local coordination handle obvious low-cost requests.

```yaml
projects:
  chatboks:
    routing_intelligence:
      enabled: true
```

Current basic behavior is conservative:

- Lightweight setup, status, routing-policy, and diagnostic questions can auto-route to Agent Zero.
- Obvious implementation requests can auto-route to Codex only.
- Obvious design, architecture, and security-analysis requests can auto-route to Claude only.
- Everything else still uses the configured mode strategy or collaboration-mode lane.

When the classifier engages, ChatBoks writes a short `[SYSTEM]` note so the auto-route is visible in `chatboks.md`.

## Help

Use `/help` in the terminal to show the local command deck in an old-school BBS-style box.

## Session Token Usage

ChatBoks shows a compact session token bar in the terminal after startup and after each agent response. The bar is
estimated from response length and tracks each configured agent against its token limit so you can spot growing context
pressure before a retry or compaction path is needed.

You can also set a session-wide warning threshold and hard cap in `config.yaml`:

```yaml
context:
  session_token_budget_warning: 220000
  session_token_budget_limit: 280000
```

When the warning threshold is crossed, ChatBoks emits a one-time system warning for the current session state. When the
hard cap is reached, new work is blocked until context is reduced.

## Cost Estimates

When an agent raises a proposal, ChatBoks now shows a rough execution estimate before you approve it. The estimate
always includes projected input/output tokens for the execution pass, and it includes USD only when that agent has
pricing configured.

```yaml
agents:
  codex:
    cost_per_million_input_tokens: 1.50
    cost_per_million_output_tokens: 6.00
    estimated_execute_output_tokens: 2000
```

`estimated_execute_output_tokens` is a planning hint for the approval gate, not a hard runtime limit. Leave the cost
fields unset when your CLI plan is flat-rate or unknown; ChatBoks will still show token estimates and mark dollar cost
as unavailable.

## Usage Baselines

ChatBoks can capture provider usage baselines into `.chatboks/usage_baselines.jsonl` with a local `/usage` command.

```text
/usage
/usage sync anthropic
/usage sync openai
/usage sync google
/usage sync all
```

Each sync opens the configured dashboard URL with Playwright CLI, captures a screenshot under
`output/playwright/usage/`, records the final URL and page title, stores a body-text excerpt, and extracts a few
usage-related highlight lines. If the page still looks like a login flow, the baseline is saved with `login_required`
so you can tell the sync reached the provider but not the actual usage screen.

Provider URLs can be overridden in `config.yaml`:

```yaml
usage_providers:
  anthropic:
    url: https://console.anthropic.com/settings/usage
```

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

To install the optional async handoff git hook for a configured project:

```powershell
python install.py taskfish --install-hook
```

The hook appends commit metadata to `chatboks.md`. If `.chatboks/state.json` has `status: "handoff"`, it invokes
ChatBoks with `--trigger=commit` so the handoff target can continue after the commit.

Run diagnostics with:

```bash
python doctor.py taskfish
```

By default, `doctor.py` avoids model-consuming calls. To test actual stdin piping through Claude/Codex, use:

```bash
python doctor.py taskfish --smoke-agents
```

For secure phone control, start the desktop-side remote bridge locally:

```bash
python remote_control.py chatboks
```

Security defaults:

- Binds to loopback only (`127.0.0.1`) and refuses non-localhost addresses.
- Uses a one-time pairing code to issue short-lived session tokens.
- Requires a bearer token on every API request.
- Keeps ChatBoks execution on the desktop that owns the repo.

The bridge serves a small mobile web UI at `http://127.0.0.1:8765/`. Pair with the printed one-time code, then send
prompts or slash commands from your phone through a private tunnel or VPN. The intended path is a private
proxy such as Tailscale Serve that forwards to the loopback bridge; do not expose this port directly to the public
internet.

Agent Zero is an optional local/bootstrap agent backed directly by Ollama. The current recommended default is
`gemma3:4b` through Ollama's local chat endpoint (`http://127.0.0.1:11434/api/chat`) with `think: false` so
responses stay in normal output instead of Ollama's separate thinking field. It is configured but not added to
project teams by default. To check Ollama/model availability and ask whether Agent Zero should join a project, run:

```bash
python install.py tinyguardian --agent-zero
```

You can also route to it directly without adding it to normal rounds:

```text
@zero check this project setup and recommend the next diagnostic command.
@agent0 check this project setup and recommend the next diagnostic command.
```

Make sure Ollama is running and the selected model exists locally, for example with `ollama pull gemma3:4b`.

Observed behavior so far:

- `gemma4:12b` was usable but too disruptive for normal desktop multitasking.
- `gemma3:4b` has been the best current balance between usefulness and workstation impact.
- Intermittent stacked-window glitches seen in the desktop app path have not been reproduced by isolated ChatBoks CLI
  role calls, so that issue appears to sit above the raw relay/model layer.

## Adapter Profiles

Claude, Codex, and Antigravity CLI flags are selected through named adapter profiles so CLI drift can be fixed in
configuration before code changes are needed.

```yaml
agents:
  codex:
    adapter_profile: codex_exec_v1
```

Known built-in profiles:

- `claude_code_print_v1`
- `codex_exec_v1`
- `agy_run_v1`

Agents can also define ordered fallback profiles for token-exhaustion recovery inside the same wrapper. This is useful
when a CLI or provider supports a lighter backup model through a different flag set:

```yaml
agents:
  gemini:
    adapter_profile: gemini_pro_v1
    fallback_profiles: [gemini_flash_v1]
```

ChatBoks keeps the same agent identity and only retries the wrapper with the next configured profile when the first
profile reports token exhaustion.

For a local CLI variant, set `adapter_args` on the agent. It overrides the named profile and supports
`{project_path}` expansion:

```yaml
agents:
  codex:
    adapter_args: ["exec", "-C", "{project_path}", "-"]
```

`doctor.py` reports the selected adapter profile and warns when a named profile is unknown.

## Optional Graphify Map

ChatBoks uses CodeGraph as the authoritative structural index for symbol lookup, call graphs, and impact analysis.
Graphify can sit alongside it as a broader architecture map that includes code plus durable project docs.

Use them for different jobs:

- **CodeGraph:** live structural work during implementation. Use it for symbol lookup, callers/callees, impact checks,
  and flow tracing. Refresh with `codegraph sync` before handoff when code changed.
- **Graphify:** slower project map for architecture orientation, durable docs, cross-file themes, community hubs, and
  exploratory questions such as "what parts of the project cluster around remote control?". Refresh after source/doc
  changes that should appear in the architecture map.

The current local setup was built with the Graphify CLI and local Ollama:

```powershell
uv tool install "graphifyy[ollama]"
graphify extract . --backend ollama --model qwen2.5-coder:3b --max-concurrency 1 --max-workers 1
$env:OLLAMA_MODEL = "qwen2.5-coder:3b"
graphify cluster-only . --backend=ollama --no-viz
graphify tree --label ChatBoks
```

Useful outputs live under `graphify-out/`:

- `GRAPH_REPORT.md`: hubs, communities, surprising links, and freshness.
- `graph.json`: queryable graph data.
- `GRAPH_TREE.html`: local interactive browser view.

After code-only changes, refresh the graph with `graphify update .`; semantic doc changes may need a local
Ollama-backed extraction rerun.

Recommended graph maintenance loop:

```powershell
codegraph sync
python doctor.py chatboks
graphify update .
graphify tree --label ChatBoks
python doctor.py chatboks
```

`doctor.py` checks that the Graphify report was built from the latest non-`graphify-out` source commit, so a separate
commit containing only refreshed Graphify artifacts does not falsely make the graph look stale.

See `GRAPH_WORKFLOW.md` for the short operational procedure.

Do not install Graphify assistant hooks by default; they can conflict with ChatBoks' CodeGraph-first workflow.

## Ollama and Local Models (third-party integration)

Agent Zero uses [Ollama](https://ollama.com/) as an optional local model runtime. The default configuration points at
`gemma3:4b`, but ChatBoks does not own, bundle, or license Ollama or the model weights. Ollama and any models
you install are third-party projects with their own licenses, terms, update cadence, storage needs, and support channels.

ChatBoks core orchestration works without Ollama. If Ollama or the selected local model is unavailable, Agent Zero can
be left out of normal rounds or marked unavailable with `/agent agent_zero blocked "Ollama is offline"`. Claude/Codex
relay features, CodeGraph context, slash commands, and approval flow remain usable.

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

ChatBoks is licensed under AGPL-3.0. CodeGraph, Ollama, and local model weights are separate third-party dependencies or
integrations governed by their own upstream licenses and terms.
