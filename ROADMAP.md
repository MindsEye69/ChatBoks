# ChatBoks Roadmap

Version: v3 handover baseline, updated June 9, 2026.

Chatboks is a local multi-agent coding orchestration system for Claude, Codex, and eventually Antigravity, with the human user as overseer. Agents collaborate through `chatboks.md`, machine state persists in `.chatboks/state.json`, and CodeGraph provides SQLite-backed codebase context.

## Current Status

- Orchestrator and agent wrappers exist.
- Claude and Codex are integrated and working on TaskFish.
- CodeGraph SQLite integration is working.
- Core signals are supported: `PROPOSAL`, `QUESTION`, `HANDOFF`, `TASK_COMPLETE`, `BLOCKED`, `SKIP`.
- Windows subprocess handling uses `.cmd`-compatible `shell=True`, stdin prompts, timeouts, `CHATBOKS=1`, `STARTUPINFO`, and `CREATE_NO_WINDOW`.
- Antigravity remains pending until the `agy` CLI is available on Windows.
- `install.py` exists as the first-run setup helper.
- `doctor.py` has dependency, CodeGraph, CLI, and optional stdin smoke checks.
- Agent Zero has an initial optional Ollama adapter, direct-only `@zero` / `@agent0` routing, and installer support. It is configured for ChatBoks but stays out of normal rounds until explicitly tagged.
- Manual collaboration outcome tracking writes wins/failures to project-local `.chatboks/outcomes.jsonl`.
- Collaboration modes are available as prompt-framing slash commands: default, brainstorm, bugsearch, implement, review, and diagnose.
- Agent availability is tracked per project with `/agent`, including exhausted/blocked status and normal-round fallbacks.
- `/help` shows a terminal command deck in a BBS-style box.
- Transcript compaction now rolls forward from `>>> SUMMARY_CHECKPOINT` boundaries while preserving the latest summary plus fresh tail context.
- Session token usage bars and per-session warning/cap thresholds are live.
- Proposal approval gates now show rough token and optional USD cost estimates.
- Role-file trust approval is enforced for project-local role files, with approved hashes stored outside the project tree.
- Agent Zero is now validated against Ollama's direct REST API with `think: false`, and `gemma3:4b` is the current best local balance between usefulness and desktop impact.

## Phase 0 - Onboarding and Compatibility

Must exist before public release.

- Embedded setup agent: Agent Zero.
- Admin-privilege first run for installing CLIs, fixing PATH, and setting environment variables.
- `chatboks doctor` diagnostic command.
- Self-healing CLI detection with adapter tests per agent.
- OAuth and API-key authentication flow, browser-based where possible.
- Versioned adapter system with per-agent YAML configs and tested CLI flag sets.
- First-run wizard that detects git repos, configures agents, and runs CodeGraph init.
- After setup, Agent Zero joins the team permanently.

## Phase 1 - Core Stability

Completed:

- Orchestrator and agent wrappers.
- Claude and Codex working.
- CodeGraph SQLite integration.
- Signal handling.
- `>>> SKIP` signal.
- `@agent` exclusive routing.
- Input buffering for incomplete user messages.
- `chatboks doctor`.
- `install.py` setup helper.
- Proposal buffering until all expected agents have had a chance to respond.
- Manual `/win`, `/fail`, `/outcome`, `/wins`, `/failures`, and `/outcomes` commands.
- Manual `/mode` command for collaboration framing.
- Manual `/agent` command for exhausted/blocked/available model status.
- Fallback routing for normal rounds when a configured agent is unavailable.
- Terminal `/help` command deck.
- Dynamic timeout.
- Automatic timeout recovery.
- Loop detection.
- Role-based router.
- Git hook for async handoffs.
- Versioned adapter system for CLI flag drift.

Remaining:

- Antigravity support when `agy` ships on Windows.

## Phase 2 - Token Intelligence

Completed:

- Role-based routing with predefined agent lanes per project.
- Collaboration-mode lane strategies such as `solo_codex`, `solo_claude`, and `full_round`.
- Conservative routing intelligence for lightweight Agent Zero, Codex-first, and Claude-first auto-routing.
- Session token usage bars plus per-session warning and hard-cap thresholds.
- Provider usage baseline capture for:
  - `console.anthropic.com/usage`
  - `platform.openai.com/usage`
  - `aistudio.google.com`

Remaining:

- Task auction / classifier refinement so Agent Zero answers more low-cost prompts without devolving into generic or bare-signal responses.
- Better token accounting from provider-native telemetry instead of response-length estimation alone.

## Phase 3 - Remote Control

- Add a websocket server to `orchestrator.py`.
- Web UI / Progressive Web App installable on Android and iOS.
- Push notifications for approval requests.
- Chat bubble UI with model logos as avatars.
- Large tap targets for APPROVE / MODIFY / REJECT on mobile.
- Orchestrator runs as a background service.
- Agents can work while the user is away.
- Native Android and iOS app later, likely React Native.

## Phase 4 - Polish and Public Release

- Ko-fi donation link in README, doctor output, setup completion screen, and terminal banner.
- GitHub Sponsors as an alternative.
- Project Gmail account for community communications.
- Launch post as an honest dev log on Dev.to and Hacker News Show HN.
- Share in Claude, OpenAI, and Antigravity communities.
- Flagship model support matrix:
  - Claude Sonnet / Opus
  - Codex
  - Antigravity
- Community adapter contributions for other models.
- Documentation site.

## Agent Zero

Agent Zero is a small local model used for coordination so frontier/cloud models are called only when needed.

Responsibilities:

- Task routing.
- Message completeness detection.
- Loop detection through git diff comparison.
- Timeout recovery and resume-prompt construction.
- Context summarization.
- Setup wizard.
- `chatboks doctor` and self-healing checks.
- Usage dashboard automation.
- Simple direct responses that do not need a cloud model.

Recommended stack:

- Base model: Gemma 3 4B, quantized
- Runtime: direct Ollama REST API
- Notes:
  - `gemma4:12b` produced better raw capability but was too disruptive on the desktop during normal use.
  - `gemma3:4b` remained light enough to run without noticeable workstation impact during mobile/remote use.
- Upgrade path: Llama 3.1 8B Q4 or another local model for users with more headroom, after desktop-impact testing.

Routing lanes:

- `claude`: architecture, security analysis, reasoning, writing, code review.
- `codex`: implementation, refactoring, testing, git operations.
- `antigravity`: browser testing, visual QA, parallel execution.
- `agent_zero`: simple queries, status checks, routing decisions, and local coordination.

Open question:

- Keep Agent Zero routing decisions under 10 seconds on Windows while improving answer quality.
- Improve Agent Zero role-call, "what's next?", and "what should I test next?" responses so they stay concrete and ChatBoks-native.
- Reproduce and isolate the intermittent stacked-window glitch in the desktop app path; isolated CLI role calls have not reproduced it so far.

## Execution Model Improvements

Dynamic timeout:

- Simple query: 120 seconds.
- Standard task: 300 seconds.
- Large task: 600 seconds.
- Massive task: 1800 seconds, with user notification before starting.
- Agent Zero may suggest splitting massive tasks instead of running them as one long call.

Automatic timeout recovery:

- Catch `subprocess.TimeoutExpired`.
- Read git diff to determine what completed before timeout.
- Build a resume prompt with completed and remaining work.
- Relaunch the agent with resume context.
- Repeat until `>>> TASK_COMPLETE` or true failure.
- The user should see the completed result, not timeout plumbing.

Loop detection:

- Compare git diffs across retry attempts.
- If 80% or more of changed lines match a previous attempt, treat the agent as looping.
- Kill the retry path and escalate to the user with a summary.
- Keep `max_auto_retries` as a final safety net.

Routing:

- `@claude`: call only Claude.
- `@codex`: call only Codex.
- `@antigravity` / `@agy`: call only Antigravity when available.
- No other agent is expected or called during an exclusive route.

Setup and diagnostics:

- `install.py` checks Node/npm, offers Node.js install via `winget`, checks global CodeGraph, offers npm install, and initializes project CodeGraph indexes when available.
- `doctor.py` validates Python dependencies, Node/npm, CodeGraph, project paths, role files, agent CLIs, CLI help, CodeGraph SQLite DBs, and optional stdin smoke tests.

Signals:

- `>>> PROPOSAL`: plan ready, needs user approval.
- `>>> QUESTION`: decision escalated to the user.
- `>>> HANDOFF`: agent passes work to the next agent.
- `>>> SKIP`: agent intentionally passes because another agent fully addressed the task.
- `>>> TASK_COMPLETE`: agent finished its portion.
- `>>> BLOCKED`: agent cannot proceed.
- `>>> SUMMARY_CHECKPOINT`: transcript compaction boundary.

## Project Notes

TaskFish:

- Windows process manager and security monitor.
- Next.js + Electron + TypeScript.
- First real Chatboks project.
- Initial two-agent collaboration completed on May 28, 2026.

Circuit 9:

- Spellstone-style card game.
- Lowest current priority, highest commercial potential.
- Natural split: Claude on game logic and balance, Codex on implementation and card data.

Tiny Guardian:

- Compact firewall with AI connection analysis.
- No git repo yet; file watcher mode only.
- Highest privacy sensitivity. Code must never leave local machine unless explicitly permitted.

IO Website:

- Website for the Informational Ontology framework.
- Claude primary.
- Antigravity handles visual QA when available.
- Future: IO-specific Claude and GPT review prose before publication.

## Immediate Next Steps

1. Commit and push the current transcript compaction, Agent Zero, trust-hardening, and documentation batch.
2. Continue refining Agent Zero direct responses for role call, routing-policy, and next-step prompts.
3. Reproduce the intermittent stacked-window desktop glitch locally while observing the visible app shell.
4. Run a fresh `python doctor.py taskfish` from the real Python environment and then a selective `--smoke-agents` pass when usage is acceptable.
5. Decide whether Agent Zero should remain direct-only by default or join more routing paths after its response quality improves.
