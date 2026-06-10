# Graph Report - chatboks  (2026-06-10)

## Corpus Check
- 84 files · ~105,051 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1155 nodes · 2926 edges · 56 communities (49 shown, 7 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 237 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3d6bcccd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
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
- [[_COMMUNITY_Community 11|Community 11]]
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
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 52|Community 52]]

## God Nodes (most connected - your core abstractions)
1. `Chatboks` - 227 edges
2. `Router` - 69 edges
3. `AgentZeroAgent` - 63 edges
4. `_router()` - 63 edges
5. `ContextBuilder` - 59 edges
6. `Stream` - 57 edges
7. `Any` - 37 edges
8. `Path` - 37 edges
9. `BaseAgent` - 34 edges
10. `Summarizer` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_outcomes.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_skills.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_slash_buffering.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_usage_sync.py → orchestrator.py
- `AgentZeroAgent` --uses--> `AgentZeroAgent`  [INFERRED]
  tests/test_security_hardening.py → agents/agent_zero.py

## Import Cycles
- 1-file cycle: `tests/test_direct_agents.py -> tests/test_direct_agents.py`
- 1-file cycle: `orchestrator.py -> orchestrator.py`

## Communities (56 total, 7 thin omitted)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (52): Agent Zero's Role - ChatBoks, Output Rules, Scope, AntigravityAgent, ClaudeAgent, CodexAgent, CodexSparkAgent, Antigravity's Role - ChatBoks (+44 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (30): Connection, ContextBuilder, Any, Path, Any, Path, Small deterministic fallback summarizer.      The design allows this to become a, Summarizer (+22 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (22): _make_app(), Chatboks, Path, Smoke tests for the local /help command., test_codegraph_status_lines_reads_sqlite_counts(), test_graph_command_renders_without_agent_round(), test_graphify_status_lines_reports_fresh_graph(), test_graphify_status_lines_reports_stale_graph() (+14 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (43): AgentZeroAgent, Path, Return the agents that should handle a user prompt.          A leading @agent pr, Router, FakeJsonResponse, _make_router(), Path, Router (+35 more)

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
Cohesion: 0.13
Nodes (32): configure_utf8_stdio(), Return an environment that makes Python children speak UTF-8., Prefer UTF-8 for ChatBoks console/process I/O on every platform., utf8_env(), append_commit_message(), git_output(), load_state(), main() (+24 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (34): datetime, RoutingDecision, _make_app(), Chatboks, Path, Smoke tests for agent availability and exhausted-agent routing., test_agent_command_marks_exhausted_without_agent_round(), test_agent_zero_can_substitute_after_main_agents_exhausted_when_allowed() (+26 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (40): clean_list(), extract_packets(), normalize_value(), packet_records_from_jsonl(), parse_packet_body(), Any, ThoughtPacket, FileSystemEventHandler (+32 more)

### Community 12 - "Community 12"
Cohesion: 0.23
Nodes (11): _make_app(), Smoke test: PROPOSAL from non-last agent is buffered; all agents run before user, Return a Chatboks instance with all I/O mocked out., QUESTION from second agent returns immediately, abandoning buffered PROPOSAL., A weak trailing agent must not override a prior completed result., First agent PROPOSAL must not short-circuit; second agent must still run., Single-agent project: PROPOSAL fires in post-loop handler (unchanged behavior)., test_blocked_after_prior_completion_is_warning_not_terminal_block() (+3 more)

### Community 13 - "Community 13"
Cohesion: 0.26
Nodes (12): FakeAgent, _make_app(), Chatboks, Path, test_model_command_escape_forces_plain_prompt_text(), test_model_command_timeout_preserves_partial_output(), test_model_commands_command_lists_registered_commands(), test_raw_model_slash_command_stays_chatboks_local() (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.33
Nodes (5): Context Priming, Escalation Triggers, Implement Mode, Quality Gate, Workflow

### Community 15 - "Community 15"
Cohesion: 0.60
Nodes (5): Bugsearch Mode, Context Priming, Escalation Triggers, Quality Gate, Workflow

### Community 16 - "Community 16"
Cohesion: 0.06
Nodes (40): BaseHTTPRequestHandler, Event, HTTPStatus, build_mobile_shell(), is_allowed_app_origin(), is_allowed_bind_host(), is_loopback_host(), is_tailnet_ipv4_host() (+32 more)

### Community 17 - "Community 17"
Cohesion: 0.14
Nodes (13): dependencies, @capacitor/android, @capacitor/core, description, devDependencies, @capacitor/cli, name, private (+5 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (28): apiFetch(), applySession(), clearSendStatusSoon(), copyLatestResponse(), currentBaseUrl(), currentPairCode(), currentToken(), describeNetworkError() (+20 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (28): apiFetch(), applySession(), clearSendStatusSoon(), copyLatestResponse(), currentBaseUrl(), currentPairCode(), currentToken(), describeNetworkError() (+20 more)

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
Cohesion: 0.40
Nodes (4): Boundaries, Codex's Role - ChatBoks, Collaboration Duties, Primary Lane

### Community 42 - "Community 42"
Cohesion: 0.26
Nodes (12): _make_app(), Chatboks, Path, Smoke tests: slash commands bypass buffer_or_complete_input., All known slash commands return immediately without buffering., A slash command typed mid-composition leaves the existing buffer intact., Non-slash text without terminal punctuation is buffered as before., handle_user_input executes slash local commands end-to-end. (+4 more)

### Community 43 - "Community 43"
Cohesion: 0.40
Nodes (4): CodeGraph, Freshness Checks, Graph Workflow, Graphify

### Community 48 - "Community 48"
Cohesion: 0.07
Nodes (44): AgentTimeoutError, BaseAgent, Any, Path, Raised when an agent CLI rejects a prompt because the context is too large., Raised when an agent CLI exceeds its idle or wall-clock timeout., TokenExhaustionError, AgentTimeoutError (+36 more)

### Community 50 - "Community 50"
Cohesion: 0.40
Nodes (4): Boundaries, Codex Spark's Role - ChatBoks, Collaboration Duties, Primary Lane

## Knowledge Gaps
- **98 isolated node(s):** `Path`, `Any`, `Any`, `appId`, `appName` (+93 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Chatboks` connect `Community 44` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 8`, `Community 10`, `Community 11`, `Community 12`, `Community 45`, `Community 46`, `Community 47`, `Community 16`, `Community 48`, `Community 49`, `Community 13`, `Community 52`, `Community 53`, `Community 42`?**
  _High betweenness centrality (0.373) - this node is a cross-community bridge._
- **Why does `Router` connect `Community 4` to `Community 0`, `Community 1`, `Community 6`, `Community 7`, `Community 10`, `Community 11`, `Community 44`, `Community 13`, `Community 46`, `Community 48`?**
  _High betweenness centrality (0.169) - this node is a cross-community bridge._
- **Why does `ContextBuilder` connect `Community 2` to `Community 0`, `Community 8`, `Community 10`, `Community 11`, `Community 44`, `Community 46`, `Community 48`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Are the 43 inferred relationships involving `Chatboks` (e.g. with `AgentZeroAgent` and `BaseHTTPRequestHandler`) actually correct?**
  _`Chatboks` has 43 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `Router` (e.g. with `AgentTimeoutError` and `datetime`) actually correct?**
  _`Router` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `AgentZeroAgent` (e.g. with `BaseAgent` and `AgentZeroAgent`) actually correct?**
  _`AgentZeroAgent` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ContextBuilder` (e.g. with `AgentTimeoutError` and `AgentZeroAgent`) actually correct?**
  _`ContextBuilder` has 17 INFERRED edges - model-reasoned connections that need verification._