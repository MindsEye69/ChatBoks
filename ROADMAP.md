# ChatBoks Roadmap

Version: v3 handover baseline, updated May 29, 2026.

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
- Agent Zero has an initial optional Ollama adapter, direct `@zero` routing, and installer support.

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

Remaining:

- Dynamic timeout.
- Automatic timeout recovery.
- Loop detection.
- Role-based router.
- Antigravity support when `agy` ships on Windows.
- Git hook for async handoffs.
- Versioned adapter system for CLI flag drift.
- Expand Agent Zero routing intelligence beyond direct local diagnostics.

## Phase 2 - Token Intelligence

- Role-based routing with predefined agent lanes per project.
- Task auction classifier: Agent Zero routes dynamically and calls cloud models only when needed.
- Session token usage bar in terminal.
- Usage baseline sync:
  - Open browser to usage dashboard.
  - Detect login state.
  - Extract usage by screenshot and vision.
- Supported dashboards:
  - `console.anthropic.com/usage`
  - `platform.openai.com/usage`
  - `aistudio.google.com`
- Cost estimation before execution.
- Token budget per session, with configurable caps and warnings.
- Transcript compaction using `>>> SUMMARY_CHECKPOINT`.

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

- Base model: Qwen2.5 Coder 3B, quantized
- Runtime: direct Ollama REST API
- Upgrade path: Llama 3.1 8B Q4 or another local model for users with 16GB+ RAM

Routing lanes:

- `claude`: architecture, security analysis, reasoning, writing, code review.
- `codex`: implementation, refactoring, testing, git operations.
- `antigravity`: browser testing, visual QA, parallel execution.
- `agent_zero`: simple queries, status checks, routing decisions, and local coordination.

Open question:

- Measure Windows CPU latency for `qwen2.5-coder:3b`; target routing decisions under 10 seconds.
- Current blocker: measure Windows CPU latency for the direct Ollama adapter and keep routing decisions under 10 seconds.

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

1. Install CodeGraph globally or add the existing CodeGraph CLI to PATH.
2. Initialize CodeGraph for the ChatBoks repo itself.
3. Run `python doctor.py taskfish` from the real Python environment with dependencies installed.
4. Test `python doctor.py taskfish --smoke-agents` when token usage is acceptable.
5. Implement dynamic timeout.
6. Implement automatic timeout recovery.
7. Implement loop detection.
8. Add session token usage bars in `ui/stream.py`.
9. Test Agent Zero latency with Ollama and Qwen2.5 Coder 3B.
