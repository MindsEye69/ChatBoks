# ChatBoks Roadmap

Version: v4 memory/remote baseline, updated June 10, 2026.

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
- Manual `/sleep` creates durable session memory under `.chatboks/sleep/`, appends a summary checkpoint, and feeds that memory back into future agent context.
- `/sleep` now acts as a work-block closure report: durable memory, CodeGraph sync attempt, Graphify freshness, git state, diagnostics hint, and `/resume` wake cue.
- `/resume` shows a visible start-of-session readiness report with graph, memory, packet, git, session, and next-action status.
- Thought Packets v1 are supported: valid `>>> PACKET` blocks are captured to `.chatboks/packets.jsonl` and used by `/sleep` as cleaner memory input.
- Session token usage bars and per-session warning/cap thresholds are live.
- Proposal approval gates now show rough token and optional USD cost estimates.
- Role-file trust approval is enforced for project-local role files, with approved hashes stored outside the project tree.
- Agent Zero is now validated against Ollama's direct REST API with `think: false`, and `gemma3:4b` is the current best local balance between usefulness and desktop impact.
- Secure mobile remote control works over a private Tailscale path with pairing/session tokens, project switching, compact mobile UI, sticky composer, latest-response/full-transcript views, and nonblocking command submission.

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
- Manual `/sleep` session-memory consolidation.
- `/sleep` closure report with memory consolidation, CodeGraph sync, Graphify freshness, git status, diagnostics hint, and `/resume` wake cue.
- `/resume` command for deliberate session rehydration: graph status, sleep memory, packet trace, git status, doctor hints, and stale-state warnings.
- Thought Packet capture and packet-aware sleep summaries.

Remaining:

- Task auction / classifier refinement so Agent Zero answers more low-cost prompts without devolving into generic or bare-signal responses.
- Better token accounting from provider-native telemetry instead of response-length estimation alone.
- Automatic light resume check at startup, with manual `/resume` for the full visible report.
- Optional automatic `/sleep` trigger after long idle periods or high transcript growth, while keeping manual `/sleep` as the explicit break marker.

## Phase 3 - Remote Control

Completed:

- Secure desktop bridge in `remote_control.py` with loopback binding by default, one-time pairing codes, short-lived session tokens, CORS/origin guard, and Tailscale-friendly serving.
- Android shell scaffolding, debug-build helper, release-signing helper, and install helper.
- Mobile remote UI supports:
  - private bridge URL
  - one-time pairing
  - saved session token
  - project picker
  - compact header
  - collapsible connection/session/token panels
  - latest response grouping
  - full transcript view
  - copy response
  - sticky composer
  - nonblocking command submission and polling
- Tailscale Serve fallback has been manually used with:
  - desktop node: `warhammer`
  - URL: `http://warhammer.tail169679.ts.net:8765`

Remaining:

- Make the desktop bridge a background service or tray process.
- Add push notifications for approval requests.
- Add approval-specific mobile controls for APPROVE / MODIFY / REJECT.
- Harden mobile connection recovery and make pairing/connection state clearer.
- Decide whether to keep the current Capacitor shell or move to a richer native/React Native app later.
- Fix local Android rebuild toolchain mismatch: Gradle currently sees OpenJDK 26, while Android tooling should use a supported JDK such as 17 or 21.

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
- Evaluate Gemma 4 QAT as the next Agent Zero model family:
  - Test `Gemma 4 E4B QAT Q4_0` first as the likely replacement for `gemma3:4b`.
  - Test `Gemma 4 E2B QAT` as the low-impact fallback if E4B affects desktop responsiveness.
  - Test `Gemma 4 12B QAT Q4_0` only as an opt-in stronger local review lane, not as the default always-on coordinator.
  - Measure cold start, first-token time, total response time, RAM/VRAM/CPU impact, desktop responsiveness, and answer quality on ChatBoks-native prompts.

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

## Memory Lifecycle

Current pieces:

- `chatboks.md`: full readable transcript.
- `.chatboks/state.json`: live machine state.
- `.chatboks/outcomes.jsonl`: manual wins/failures.
- `.chatboks/packets.jsonl`: structured Thought Packets captured from agent responses.
- `.chatboks/sleep/latest.md`: latest durable sleep memory.
- `.chatboks/sleep/history.jsonl`: sleep memory history.

Implemented:

- `/sleep` runs deterministic consolidation, writes sleep artifacts, appends a `>>> SUMMARY_CHECKPOINT`, and injects latest sleep memory into future context.
- `/sleep` also runs a safe closure checklist: CodeGraph sync attempt, Graphify freshness, git status, diagnostics hint, and `/resume` wake cue.
- `/resume` provides a visible rehydration command that checks CodeGraph, Graphify, sleep memory, packet memory, git status, session state, and doctor hints.
- Thought Packet blocks are optional but parsed when agents emit them.
- Packet memory improves `/sleep` by preserving observed facts, risks, next actions, and unresolved signals more cleanly than transcript scraping.

Planned:

- Startup light resume: automatically check for stale graphs/memory without doing expensive work or flooding the terminal.
- End-of-session `/sleep`: optional heavier closure modes that can refresh Graphify, run doctor/tests, and mark a clean break.
- Packet-driven confirmation: use packet `risks` and `observed` fields as verifier checklists.
- Mobile remote trace view: optional Agent Trace / Packet Trace panel after backend behavior settles.

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

1. Use Thought Packets in confirmation mode:
   - verifier sees executor `observed` and `risks`
   - unresolved risks prevent silent completion
2. Run a ChatBoks multi-agent review of Thought Packets and sleep/resume lifecycle.
3. Add optional heavier `/sleep` modes for Graphify refresh, doctor, and focused tests.
4. Continue refining Agent Zero direct responses for role call, routing-policy, next-step prompts, and packet-aware summaries.
5. Run an Agent Zero model bake-off with Gemma 4 QAT:
   - current `gemma3:4b` baseline
   - `Gemma 4 E4B QAT Q4_0`
   - `Gemma 4 E2B QAT`
   - optional `Gemma 4 12B QAT Q4_0` under explicit desktop-impact observation
6. Reproduce and isolate the intermittent stacked-window desktop glitch if it returns.
7. Preserve the original user request separately from the repair prompt in confirmation mode, so second-pass verifier prompts show both the initial goal and the current repair request.
8. Improve mobile remote polish:
   - connection recovery feedback
   - approval controls
   - optional Agent Trace / Packet Trace view
9. Fix Android rebuild JDK selection so APK builds consistently use a supported JDK.
