# ChatBoks Tool Trust Ledger and Privacy Contract

Last reviewed: 2026-06-15

Status: planning/security contract. This document is normative for ChatBoks planning, but it does not implement automation, cloud/local routing, MCP registry ingestion, or new tool discovery.

## Scope

This contract defines the trust boundaries for ChatBoks tool execution, MCP-style context providers, local-model privacy, durable memory, logs, and future cloud fallback. It applies to the ChatBoks repo and the projects explicitly listed in `config.yaml`.

ChatBoks is a human-supervised local relay. Tools and models may still execute commands, read files, call local services, open browser sessions, or send prompts to third-party provider CLIs. "Local" only describes where a process runs; it does not by itself define what context is assembled, retained, logged, or sent onward.

## Allowed Projects

The current project allowlist is the set of project paths in `config.yaml`:

| Project | Path | Notes |
|---|---|---|
| chatboks | `C:\Users\MindsEye\Desktop\chatboks` | Primary repo for this contract. |
| taskfish | `C:\Users\MindsEye\Desktop\Tasker\tasker-poc` | CodeGraph-enabled project. |
| circuit9 | `C:\Users\MindsEye\Desktop\CircuitNine` | CodeGraph-enabled project. |
| tinyguardian | `C:\Users\MindsEye\source\repos\TinyGuardian` | Highest privacy sensitivity; no cloud sharing unless explicitly permitted for the specific task. |
| io-website | `C:\Users\MindsEye\Desktop\Information Ontology` | Publication/content project. |
| biosassist | `C:\Users\MindsEye\Desktop\BiosAssist\Repo` | Coordinator/Claude project. |
| klippii | `C:\Users\MindsEye\Desktop\Klippii` | CodeGraph-enabled project. |
| wallvision | `C:\Users\MindsEye\Desktop\WallVision` | CodeGraph-enabled project. |

Adding a project to this list expands the possible filesystem context ChatBoks may package for agents. It requires human review of the project path, agent roster, role files, and sensitivity level before use.

## Tool Trust Ledger

| Tool or server | Source | Command surface | Filesystem scope | Network scope | Auth and secrets handling | Allowed projects | Review date | Risk class |
|---|---|---|---|---|---|---|---|---|
| CodeGraph MCP / CodeGraph SQLite context | Project instructions and `.codegraph/codegraph.db`; upstream `@colbymchenry/codegraph` | MCP queries for symbols, call graphs, file lists, context, and traces; optional `codegraph sync` CLI | Reads each configured project's `.codegraph` database and, during sync, parses the project tree | No runtime network expected for local queries; install/update may use npm | Does not need provider secrets. It can expose code structure and filenames to agents through context. | Projects with `codegraph: true` in `config.yaml` | 2026-06-15 | Medium: broad code visibility, low command authority |
| Claude CLI agent | `config.yaml` agent `claude`, local `claude.cmd` | Provider CLI invocation, registered `@claude /ultrareview` subcommand | Receives packaged context from ChatBoks and may propose or perform edits when approved | Cloud provider network through the Claude CLI | Provider auth is owned by the CLI environment, not ChatBoks. Secrets must not be pasted into prompts or durable memory unless explicitly required and approved. | Projects whose agent roster includes `claude` | 2026-06-15 | High: cloud prompt exposure and code-edit capability |
| Codex CLI agent | `config.yaml` agent `codex`, local `codex.cmd` | Provider CLI invocation with Codex adapter profile | Receives packaged context from ChatBoks and may edit files, run tests, and use git when requested | Cloud provider network through Codex CLI unless the configured runtime is local | Provider auth is owned by the CLI environment. Secrets must stay out of prompts, logs, packets, and sleep summaries unless explicitly approved. | Projects whose agent roster includes `codex` | 2026-06-15 | High: cloud prompt exposure, shell/file authority through agent work |
| Codex Spark lane | `config.yaml` direct agent `codex_spark` | Codex CLI with lighter adapter profile | Same as Codex, but intended for smaller scoped work | Same as Codex CLI | Same as Codex CLI | Direct-tag use only unless explicitly routed | 2026-06-15 | High: same trust class as Codex CLI |
| Coordinator local model | `config.yaml` agent `coordinator`, Ollama endpoint `http://127.0.0.1:11434/api/chat` | Ollama chat request only; no tools by design | Receives compact ChatBoks context, capped by `max_prompt_chars` | Loopback Ollama endpoint only under current config | No provider auth. Model prompts may still contain repo facts, user instructions, memory summaries, and packet-derived observations. | Direct use and configured fallback use only | 2026-06-15 | Medium: local prompt privacy, low execution authority |
| Antigravity agent placeholder | `config.yaml` agent `antigravity`, CLI `agy` | Planned CLI invocation when available | Not active until CLI exists and is reviewed | Unknown until available | Unknown; must be reviewed before activation | None yet | 2026-06-15 | High until reviewed |
| Graphify | README/roadmap optional local architecture map | `graphify extract`, `graphify update`, `graphify tree`, local Ollama backend | Reads project code and docs; writes `graphify-out/` artifacts | Local Ollama when configured; package install/update may use external registries | No provider secret required for local backend. Generated graph artifacts may retain semantic summaries of code/docs. | Manual use for ChatBoks and other reviewed projects | 2026-06-15 | Medium: derived architecture memory |
| Playwright usage sync | README `/usage sync` workflow | Browser automation to configured provider dashboards | Writes screenshots and excerpts under `.chatboks`/output paths | Provider dashboard URLs such as Anthropic, OpenAI, and Google usage pages | Uses existing browser/session auth. Screenshots or excerpts may reveal account metadata and usage data. | Manual `/usage sync` only | 2026-06-15 | High: authenticated browser data capture |
| Mobile remote bridge | `remote_control.py`, README remote control section | Local HTTP bridge for prompts, polling, pairing, project switching | Runs on the desktop that owns the repo; reads/writes ChatBoks project state and transcript through normal orchestrator paths | Loopback by default; private tunnel/VPN such as Tailscale Serve may forward to it | One-time pairing code issues short-lived bearer tokens. Do not expose directly to the public internet. | Configured projects exposed through the bridge UI | 2026-06-15 | High: remote prompt/control surface |
| Role-file trust loader | `trust.py` | Loads project-local role files after hash approval | Reads role files inside project root; stores approved hashes under `~/.chatboks/approved-roles` | None | Stores hashes, not role contents. Hash approval is per project path and role filename. | All configured projects with role files | 2026-06-15 | Medium: prompt-injection guard |
| Shell/test/git commands run by agents | Codex/Claude implementation work | Commands requested by the user or needed for verification | Current repo by default; broader filesystem only when the task requires it | Depends on command; package managers, browser tools, and CLIs may use network | Agents must not print, persist, or transmit secrets unnecessarily. Destructive commands require explicit user request. | Current working project unless explicitly changed | 2026-06-15 | High: direct machine-state authority |

### Session-Available Connectors

Some Codex sessions may expose app MCP connectors such as Figma, Hugging Face, Neon Postgres, Browser, Vercel, PDF, Documents, Presentations, or Spreadsheets. These are not ChatBoks runtime integrations unless a user explicitly invokes them for a task. They are treated as external authenticated/cloud-capable surfaces, with these default rules:

- Do not use a connector just because it is available.
- Do not move ChatBoks memory, packets, logs, or project code into a connector unless the user request requires it.
- Do not persist connector-derived credentials or tokens in ChatBoks docs, packets, sleep summaries, Graphify artifacts, or logs.
- Record any durable connector adoption in this ledger before making it automatic.

## Privacy Boundaries

### Coordinator

Coordinator is intended to be local, cheap, and tool-less. It may receive:

- Active task text.
- Round context and handoff state.
- Recent ChatBoks transcript excerpts.
- CodeGraph status in lean mode.
- Sleep memory and packet-derived facts when present.

Coordinator must not receive:

- Raw secrets, API keys, tokens, cookies, private keys, or password material.
- Full project dumps unless the user explicitly asks for a deeper local-model analysis.
- Authenticated browser captures or provider account screenshots unless the user explicitly approves that exact use.

Coordinator output may be written to `chatboks.md` and may be summarized into sleep memory or packet-derived memory if later captured by the normal ChatBoks workflow.

### Packet Memory

Thought Packets are retained in `.chatboks/packets.jsonl`. They may include agent, stance, observed facts, risks, next action, signal, and orchestration context.

Retention rules:

- Anchored observations can be promoted into verified facts during sleep summarization.
- Unanchored observations are downgraded during summarization and should not be treated as durable truth.
- Risks and next actions may be preserved across `/sleep` and `/resume`.
- Packets must not contain secrets, bearer tokens, private URLs, full credentials, or unnecessary personal data.

Deletion expectation:

- The user can delete `.chatboks/packets.jsonl` to remove packet memory for a project.
- After deletion, future sleep summaries must not rely on the deleted packet file, but already-written sleep summaries may still contain previously summarized facts unless those summaries are also deleted or rewritten.

### Sleep Summaries and Resume Memory

Sleep memory is retained under `.chatboks/sleep/`, including `latest.md`, `history.jsonl`, and metadata files. It is loaded into future agent context.

Retained content may include:

- Decisions, outcomes, blockers, next actions, test results, file references, and verified packet facts.
- Downgraded observations and open risks when relevant.
- High-level summaries of prior transcript content.

Deletion expectation:

- The user can delete `.chatboks/sleep/` to remove durable sleep memory for a project.
- The full transcript may still contain the original source lines unless `chatboks.md` is also edited or archived.
- If a summary contains sensitive content, delete or rewrite both the summary artifact and any transcript source that can regenerate it.

Consent required:

- Before including secrets, private customer data, medical/legal/financial records, proprietary third-party data, or authenticated provider dashboard data in sleep memory.
- Before using sleep memory from one project as context for another project.

### Coordinator Summaries and Transcript Compaction

Transcript compaction may append `>>> SUMMARY_CHECKPOINT` blocks to `chatboks.md`. These blocks are durable transcript content, not temporary cache.

Retained content may include:

- Prior memory, wins/failures, decisions, risks, and active task state.
- References to files and commands used as evidence.

Deletion expectation:

- The user can edit or delete summary checkpoints from `chatboks.md`, but should treat this as changing historical context for future agents.
- Sensitive material should be removed at the source transcript line and from any derived checkpoint.

### Graphify

Graphify produces durable architecture artifacts under `graphify-out/`, including `GRAPH_REPORT.md`, `graph.json`, and `GRAPH_TREE.html`.

Retained content may include:

- Code and doc entity names.
- Derived semantic clusters, summaries, relationships, and architecture labels.
- Paths and identifiers that reveal project structure.

Deletion expectation:

- The user can delete `graphify-out/` to remove Graphify artifacts.
- Regenerating Graphify may recreate derived summaries from current code and docs.

Consent required:

- Before running Graphify on a project with sensitive regulated data, private customer data, or third-party confidential source that has not been cleared for derived local indexing.
- Before using a non-local Graphify backend.

### Logs and Local State

ChatBoks may retain:

- `chatboks.md`: readable transcript.
- `.chatboks/state.json`: current orchestration state.
- `.chatboks/outcomes.jsonl`: manually recorded wins/failures.
- `.chatboks/agent_status.json`: agent availability.
- `.chatboks/usage_baselines.jsonl` and usage screenshots/excerpts when `/usage sync` is used.
- Test, build, and command output quoted by agents in the transcript.

Deletion expectation:

- Project-local `.chatboks` files can be deleted to clear local operational memory, with the tradeoff that resume, availability, outcomes, and diagnostics history are lost.
- `chatboks.md` remains the primary durable conversation record unless archived or edited by the user.

### Local Models

Local model runtimes may process prompts containing project context, memory summaries, and user instructions. Local execution does not permit unrestricted context assembly.

Rules:

- Keep local prompts scoped to the current task.
- Prefer lean context for routing, status, and diagnostics.
- Do not include secrets or unrelated project context.
- Treat model caches, runtime logs, and backend telemetry as part of the local privacy boundary and review them before claiming no retention.

### Cloud Fallback

Cloud fallback means sending task context to a provider-backed CLI, hosted model, connector, or external service. It is allowed only when one of these explicit triggers applies:

- The user directly routes to a cloud agent or connector, such as Claude, Codex, Figma, Hugging Face, Neon, or Vercel.
- The configured project mode or agent roster selects a cloud-backed agent for the task.
- The user approves a proposal that clearly names the cloud-backed agent or service.
- A local Coordinator response explicitly recommends handoff and the user or existing ChatBoks routing policy proceeds with that cloud agent.

Cloud fallback requires explicit user consent before including:

- Secrets, credentials, tokens, cookies, or private keys.
- Sensitive personal data, regulated data, customer data, or private medical/legal/financial details.
- Authenticated dashboard screenshots or account metadata.
- Cross-project memory or context from a project other than the active one.
- Large source snapshots beyond the scoped files needed for the task.

Cloud fallback must not be automatic until the "not allowed yet" items below are resolved and implemented with visible consent.

## Retention and Deletion Summary

| Data class | Where retained | Can be deleted by user | Consent required before retention or sharing |
|---|---|---|---|
| Full transcript | `chatboks.md` | Yes, by editing/archiving/deleting | For secrets or sensitive third-party/private data |
| Live state | `.chatboks/state.json` | Yes | No, unless it contains sensitive task text |
| Packet memory | `.chatboks/packets.jsonl` | Yes | For secrets, private data, or cross-project facts |
| Sleep memory | `.chatboks/sleep/` | Yes | For sensitive content and cross-project reuse |
| Outcomes | `.chatboks/outcomes.jsonl` | Yes | For sensitive descriptions |
| Usage baselines | `.chatboks/usage_baselines.jsonl`, screenshots/excerpts | Yes | Always before authenticated dashboard capture |
| CodeGraph index | `.codegraph/` | Yes, regenerate with CodeGraph | Before indexing unusually sensitive projects |
| Graphify artifacts | `graphify-out/` | Yes, regenerate with Graphify | Before sensitive-project indexing or non-local backend use |
| Role approval hashes | `~/.chatboks/approved-roles/` | Yes | User approval is required to create/update hashes |
| Provider CLI auth | Provider CLI/browser stores outside ChatBoks | Managed outside ChatBoks | Never copy into ChatBoks memory or docs |

## Not Allowed Yet

The following are explicitly out of scope until a separate reviewed design and implementation exists:

- MCP registry auto-ingestion.
- Automatic installation or activation of MCP servers from registry metadata.
- MCP server trust scoring without manual ledger review.
- Automatic cloud/local routing based only on model availability, latency, or cost.
- Automatic cloud fallback after local model failure.
- Cross-project memory reuse without a user-visible consent mechanism.
- Silent inclusion of `.chatboks` memory, Graphify artifacts, usage screenshots, or authenticated dashboard excerpts in cloud prompts.
- Background mobile bridge exposure outside loopback/private tunnel controls.

## Review Procedure

Review this ledger when:

- A new project is added to `config.yaml`.
- A new agent, connector, MCP server, local model runtime, browser automation path, or remote-control surface is added.
- A tool gains broader filesystem, shell, network, or auth access.
- Cloud/local routing behavior changes.
- Packet, sleep, Graphify, usage, or transcript retention changes.

Each review should update the date, risk class, allowed projects, and consent requirements for the affected entry.
