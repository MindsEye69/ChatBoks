# Graph Report - chatboks  (2026-06-12)

## Corpus Check
- 92 files · ~298,747 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1399 nodes · 3549 edges · 72 communities (61 shown, 11 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 260 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `85113bb1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 73|Community 73]]

## God Nodes (most connected - your core abstractions)
1. `Chatboks` - 253 edges
2. `Stream` - 75 edges
3. `Router` - 70 edges
4. `AgentZeroAgent` - 65 edges
5. `_router()` - 63 edges
6. `ContextBuilder` - 62 edges
7. `Any` - 47 edges
8. `BaseAgent` - 39 edges
9. `Path` - 38 edges
10. `RoutingDecision` - 35 edges

## Surprising Connections (you probably didn't know these)
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_latency.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_outcomes.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_skills.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_slash_buffering.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_usage_sync.py → orchestrator.py

## Import Cycles
- 1-file cycle: `tests/test_direct_agents.py -> tests/test_direct_agents.py`
- 1-file cycle: `orchestrator.py -> orchestrator.py`

## Communities (72 total, 11 thin omitted)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (54): Agent Zero's Role - ChatBoks, Output Rules, Scope, AntigravityAgent, ClaudeAgent, CodexAgent, CodexSparkAgent, Antigravity's Role - ChatBoks (+46 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (34): Connection, ContextBuilder, Any, Path, Any, Path, Small deterministic fallback summarizer.      The design allows this to become a, Summarizer (+26 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (24): _make_app(), Chatboks, Path, Smoke tests for the local /help command., test_codegraph_status_lines_reads_sqlite_counts(), test_graph_command_renders_without_agent_round(), test_graphify_status_lines_reports_fresh_graph(), test_graphify_status_lines_reports_stale_graph() (+16 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (45): AgentZeroAgent, Any, Path, Return the agents that should handle a user prompt.          A leading @agent pr, Router, FakeJsonResponse, _make_router(), Path (+37 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (39): Credits, Workflow Inspirations, Agent Availability, ChatBoks, CodeGraph (third-party integration), Collaboration Modes, Cost Estimates, Early Development Notice (+31 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (64): _config(), Dedicated unit tests for Router and RoutingDecision., _router(), test_after_returns_next_agent(), test_after_returns_you_at_end_of_list(), test_after_unknown_agent_returns_primary(), test_auto_route_claude_for_analysis_prompt(), test_auto_route_claude_suppressed_when_prompt_contains_implement() (+56 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (38): _approval_dir(), Path, Tests for F3: trusted role-file approval (trust.py).  Covers: - First approval:, test_approval_pin_is_stored_outside_project(), test_first_approval_interactive_hash_stored_after_approval(), test_first_approval_interactive_user_approves_returns_content(), test_hash_match_non_interactive_returns_content(), test_hash_match_returns_content_without_prompting() (+30 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (24): AgentZeroAgent, ContextBuilder, _make_agent_zero(), _make_app(), _make_builder(), Chatboks, Path, Smoke tests for security hardening pass 1.  Covers: - chatboks.md history marked (+16 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (62): clean_list(), extract_packets(), has_source_anchor(), normalize_value(), packet_records_from_jsonl(), parse_packet_body(), Any, split_observed_by_anchor() (+54 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (40): datetime, RoutingDecision, _make_app(), Chatboks, Path, Smoke tests for agent availability and exhausted-agent routing., test_agent_command_marks_exhausted_without_agent_round(), test_agent_zero_can_substitute_after_main_agents_exhausted_when_allowed() (+32 more)

### Community 12 - "Community 12"
Cohesion: 0.23
Nodes (11): _make_app(), Smoke test: PROPOSAL from non-last agent is buffered; all agents run before user, Return a Chatboks instance with all I/O mocked out., QUESTION from second agent returns immediately, abandoning buffered PROPOSAL., A weak trailing agent must not override a prior completed result., First agent PROPOSAL must not short-circuit; second agent must still run., Single-agent project: PROPOSAL fires in post-loop handler (unchanged behavior)., test_blocked_after_prior_completion_is_warning_not_terminal_block() (+3 more)

### Community 13 - "Community 13"
Cohesion: 0.17
Nodes (10): Event, RemoteEventBuffer, RemoteBridgeServer, BlockingFakeApp, FakeStream, test_remote_event_buffer_preserves_stream_delta_whitespace(), test_remote_session_snapshot_includes_compact_proposal(), test_remote_session_snapshot_includes_trace_payload() (+2 more)

### Community 14 - "Community 14"
Cohesion: 0.33
Nodes (5): Context Priming, Escalation Triggers, Implement Mode, Quality Gate, Workflow

### Community 15 - "Community 15"
Cohesion: 0.60
Nodes (5): Bugsearch Mode, Context Priming, Escalation Triggers, Quality Gate, Workflow

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (28): rotate_pair_code_from_operator_file(), FakeSession, Path, run_server(), test_codegraph_stats_reads_counts_from_database(), test_git_environment_returns_none_for_non_repo(), test_packet_trace_reads_compact_packet_records(), test_parse_chatboks_messages_reads_multiline_turns() (+20 more)

### Community 17 - "Community 17"
Cohesion: 0.14
Nodes (13): dependencies, @capacitor/android, @capacitor/core, description, devDependencies, @capacitor/cli, name, private (+5 more)

### Community 18 - "Community 18"
Cohesion: 0.09
Nodes (42): apiFetch(), appendStreamText(), applyEventToList(), applySession(), clearSendStatusSoon(), copyLatestResponse(), currentBaseUrl(), currentPairCode() (+34 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (49): agentDisplayName(), apiFetch(), appendStreamText(), applyEventToList(), applySession(), clearSendStatusSoon(), copyLatestResponse(), currentBaseUrl() (+41 more)

### Community 20 - "Community 20"
Cohesion: 0.25
Nodes (7): appId, appName, server, allowNavigation, androidScheme, cleartext, webDir

### Community 21 - "Community 21"
Cohesion: 0.25
Nodes (7): Adversarial Pressure, ChatBoks Collaboration Protocol, Contribution Stance, Coordination Rules, Evidence Standard, Signals, Thought Packets

### Community 22 - "Community 22"
Cohesion: 0.25
Nodes (7): appId, appName, server, allowNavigation, androidScheme, cleartext, webDir

### Community 23 - "Community 23"
Cohesion: 0.33
Nodes (5): Android build, ChatBoks Remote Android Shell, Desktop side, Early Development Notice, Notes

### Community 24 - "Community 24"
Cohesion: 0.33
Nodes (5): Boundaries, Codex's Role - ChatBoks, Collaboration Duties, Primary Lane, Tooling Safety

### Community 42 - "Community 42"
Cohesion: 0.33
Nodes (7): _make_app(), Chatboks, Path, Smoke tests for usage baseline syncing and summaries., test_usage_show_reports_no_records_yet(), test_usage_summary_reads_saved_jsonl(), test_usage_sync_records_playwright_capture_metadata()

### Community 43 - "Community 43"
Cohesion: 0.40
Nodes (4): CodeGraph, Freshness Checks, Graph Workflow, Graphify

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (13): agent_trace_from_transcript(), compact_summary(), detect_tailnet_ip(), is_allowed_bind_host(), is_loopback_host(), is_tailnet_ipv4_host(), monitor_stats(), parse_query_int() (+5 more)

### Community 48 - "Community 48"
Cohesion: 0.10
Nodes (23): BaseAgent, Any, Path, Raised when an agent CLI rejects a prompt because the context is too large., TokenExhaustionError, Popen, Queue, RuntimeError (+15 more)

### Community 50 - "Community 50"
Cohesion: 0.33
Nodes (5): Boundaries, Codex Spark's Role - ChatBoks, Collaboration Duties, Primary Lane, Tooling Safety

### Community 51 - "Community 51"
Cohesion: 0.31
Nodes (4): HTTPStatus, is_allowed_app_origin(), RemoteHandler, test_allowed_app_origin_accepts_localhost_with_optional_ports()

### Community 56 - "Community 56"
Cohesion: 0.19
Nodes (13): BaseHTTPRequestHandler, build_token_usage(), codegraph_stats(), git_environment(), packet_trace_from_file(), parse_chatboks_messages(), proposal_snapshot(), Any (+5 more)

### Community 57 - "Community 57"
Cohesion: 0.46
Nodes (7): _make_app(), Chatboks, Path, Smoke tests for manual collaboration outcome tracking., test_outcomes_summary_reads_jsonl(), test_suggest_outcome_uses_agent_zero_without_recording_jsonl(), test_win_command_records_jsonl_without_agent_round()

### Community 58 - "Community 58"
Cohesion: 0.26
Nodes (12): _make_app(), Chatboks, Path, Smoke tests: slash commands bypass buffer_or_complete_input., All known slash commands return immediately without buffering., A slash command typed mid-composition leaves the existing buffer intact., Non-slash text without terminal punctuation is buffered as before., handle_user_input executes slash local commands end-to-end. (+4 more)

### Community 59 - "Community 59"
Cohesion: 0.18
Nodes (10): ChatBoks Interface Handoff, Current Mobile Remote UI Notes, Current Repo State, Fresh Chat Prompt, Interface Direction, Security Scan Findings To Keep In Mind, Suggested Next Work, Terminal / Mini-Terminal Idea (+2 more)

### Community 62 - "Community 62"
Cohesion: 0.20
Nodes (9): ChatBoks Mobile Remote Pairing Runbook, Generate A New Pairing Code, How Pairing Works, If The Command Cannot Find The Operator File, Public Safety, Relevant Tests, Start The Bridge, Troubleshooting (+1 more)

### Community 63 - "Community 63"
Cohesion: 0.08
Nodes (52): agentDisplayName(), agentGlyph(), apiFetch(), apiUrl(), applySession(), connect(), DEFAULT_AGENTS, els (+44 more)

### Community 64 - "Community 64"
Cohesion: 0.39
Nodes (6): _make_app(), Chatboks, Path, Smoke tests for local CLI latency summaries., test_latency_reports_no_records_yet(), test_latency_summary_reads_recent_jsonl_records()

### Community 69 - "Community 69"
Cohesion: 0.40
Nodes (3): promptInput, terminalFocus, themeToggle

### Community 71 - "Community 71"
Cohesion: 0.12
Nodes (37): AgentTimeoutError, Raised when an agent CLI exceeds its idle or wall-clock timeout., AgentTimeoutError, FakeAgent, _make_app(), Chatboks, Path, test_model_command_escape_forces_plain_prompt_text() (+29 more)

### Community 73 - "Community 73"
Cohesion: 0.23
Nodes (5): default_operator_status_path(), main(), RemoteAuth, RemoteBridgeServer, ThreadingHTTPServer

## Knowledge Gaps
- **130 isolated node(s):** `version`, `configurations`, `allow`, `Path`, `Any` (+125 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Chatboks` connect `Community 44` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 42`, `Community 45`, `Community 46`, `Community 47`, `Community 48`, `Community 49`, `Community 51`, `Community 52`, `Community 53`, `Community 56`, `Community 57`, `Community 58`, `Community 61`, `Community 64`, `Community 65`, `Community 66`, `Community 67`, `Community 71`, `Community 73`?**
  _High betweenness centrality (0.322) - this node is a cross-community bridge._
- **Why does `Router` connect `Community 4` to `Community 1`, `Community 65`, `Community 67`, `Community 6`, `Community 71`, `Community 7`, `Community 9`, `Community 10`, `Community 44`, `Community 46`, `Community 61`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Why does `Stream` connect `Community 3` to `Community 65`, `Community 67`, `Community 71`, `Community 9`, `Community 10`, `Community 73`, `Community 44`, `Community 13`, `Community 46`, `Community 47`, `Community 49`, `Community 51`, `Community 56`, `Community 61`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Are the 47 inferred relationships involving `Chatboks` (e.g. with `AgentZeroAgent` and `BaseHTTPRequestHandler`) actually correct?**
  _`Chatboks` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `Stream` (e.g. with `AgentTimeoutError` and `BaseHTTPRequestHandler`) actually correct?**
  _`Stream` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `Router` (e.g. with `AgentTimeoutError` and `datetime`) actually correct?**
  _`Router` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `AgentZeroAgent` (e.g. with `BaseAgent` and `AgentZeroAgent`) actually correct?**
  _`AgentZeroAgent` has 18 INFERRED edges - model-reasoned connections that need verification._