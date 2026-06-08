# Graph Report - .  (2026-06-08)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 474 nodes · 1164 edges · 17 communities
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 99 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3f0536f1`
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

## God Nodes (most connected - your core abstractions)
1. `Chatboks` - 109 edges
2. `ContextBuilder` - 48 edges
3. `Stream` - 34 edges
4. `AgentZeroAgent` - 32 edges
5. `Router` - 30 edges
6. `BaseAgent` - 25 edges
7. `load_role_with_approval()` - 22 edges
8. `Any` - 22 edges
9. `AgentTimeoutError` - 21 edges
10. `Path` - 20 edges

## Surprising Connections (you probably didn't know these)
- `# TODO: Verify Antigravity/agy non-interactive flags against the installed CLI.` --rationale_for--> `Antigravity`  [EXTRACTED]
  agents/antigravity.py → ANTIGRAVITY.md
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_agent_status.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_outcomes.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_skills.py → orchestrator.py
- `Chatboks` --uses--> `Chatboks`  [INFERRED]
  tests/test_slash_buffering.py → orchestrator.py

## Import Cycles
- 1-file cycle: `orchestrator.py -> orchestrator.py`
- 1-file cycle: `tests/test_direct_agents.py -> tests/test_direct_agents.py`

## Communities (17 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (4): Any, Chatboks, main(), Path

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (36): Agent Zero's Role - ChatBoks, Output Rules, Scope, AgentZeroAgent, Path, AntigravityAgent, # TODO: Verify Antigravity/agy non-interactive flags against the installed CLI., BaseAgent (+28 more)

### Community 2 - "Community 2"
Cohesion: 0.10
Nodes (21): Connection, ContextBuilder, Any, Path, Path, Small deterministic fallback summarizer.      The design allows this to become a, Context Modes, _make_codegraph() (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (31): Credits, Workflow Inspirations, Agent Availability, ChatBoks, CodeGraph (third-party integration), Collaboration Modes, Files, Help (+23 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (12): FileSystemEventHandler, ChatboksFileHandler, Watch chatboks.md for external handoff changes., _make_app(), Chatboks, Path, Smoke tests for the local /help command., test_help_command_renders_without_agent_round() (+4 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (30): AgentTimeoutError, Raised when an agent CLI rejects a prompt because the context is too large., Raised when an agent CLI exceeds its idle or wall-clock timeout., TokenExhaustionError, AgentTimeoutError, Chatboks, RuntimeError, Path (+22 more)

### Community 6 - "Community 6"
Cohesion: 0.19
Nodes (32): _approval_dir(), Path, Tests for F3: trusted role-file approval (trust.py).  Covers: - First approval:, test_approval_pin_is_stored_outside_project(), test_first_approval_interactive_hash_stored_after_approval(), test_first_approval_interactive_user_approves_returns_content(), test_hash_match_non_interactive_returns_content(), test_hash_match_returns_content_without_prompting() (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (24): AgentZeroAgent, ContextBuilder, _make_agent_zero(), _make_app(), _make_builder(), Chatboks, Path, Smoke tests for security hardening pass 1.  Covers: - chatboks.md history marked (+16 more)

### Community 8 - "Community 8"
Cohesion: 0.26
Nodes (18): CompletedProcess, check_agent(), check_agent_zero(), check_cli_help(), check_node_and_codegraph(), check_project(), check_python_deps(), default_config_path() (+10 more)

### Community 9 - "Community 9"
Cohesion: 0.35
Nodes (15): ask(), default_config_path(), ensure_agent_zero_ollama(), ensure_codegraph(), ensure_node(), ensure_project_codegraph(), fetch_ollama_models(), find_codegraph_command() (+7 more)

### Community 10 - "Community 10"
Cohesion: 0.32
Nodes (12): datetime, _make_app(), Chatboks, Path, Smoke tests for agent availability and exhausted-agent routing., test_agent_command_marks_exhausted_without_agent_round(), test_agent_zero_can_substitute_after_main_agents_exhausted_when_allowed(), test_direct_fallback_must_be_allowed_to_fill_main_seat() (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.26
Nodes (12): _make_app(), Chatboks, Path, Smoke tests: slash commands bypass buffer_or_complete_input., All known slash commands return immediately without buffering., A slash command typed mid-composition leaves the existing buffer intact., Non-slash text without terminal punctuation is buffered as before., handle_user_input executes slash local commands end-to-end. (+4 more)

### Community 12 - "Community 12"
Cohesion: 0.27
Nodes (9): _make_app(), Smoke test: PROPOSAL from non-last agent is buffered; all agents run before user, Return a Chatboks instance with all I/O mocked out., QUESTION from second agent returns immediately, abandoning buffered PROPOSAL., First agent PROPOSAL must not short-circuit; second agent must still run., Single-agent project: PROPOSAL fires in post-loop handler (unchanged behavior)., test_proposal_buffered_until_all_agents_complete(), test_question_after_proposal_abandons_buffer() (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.39
Nodes (6): _make_app(), Chatboks, Path, Smoke tests for native ChatBoks skill discovery., test_skills_command_lists_native_skills_without_agent_round(), test_skills_command_previews_requested_skill()

### Community 14 - "Community 14"
Cohesion: 0.48
Nodes (6): _make_app(), Chatboks, Path, Smoke tests for manual collaboration outcome tracking., test_outcomes_summary_reads_jsonl(), test_win_command_records_jsonl_without_agent_round()

### Community 15 - "Community 15"
Cohesion: 0.33
Nodes (5): Context Priming, Escalation Triggers, Implement Mode, Quality Gate, Workflow

### Community 16 - "Community 16"
Cohesion: 0.40
Nodes (4): Context Priming, Escalation Triggers, Quality Gate, Workflow

## Knowledge Gaps
- **44 isolated node(s):** `Path`, `Path`, `CompletedProcess`, `Any`, `Text` (+39 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Chatboks` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 7`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`?**
  _High betweenness centrality (0.396) - this node is a cross-community bridge._
- **Why does `ContextBuilder` connect `Community 2` to `Community 0`, `Community 4`, `Community 5`, `Community 7`, `Community 10`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Why does `Router` connect `Community 1` to `Community 0`, `Community 4`, `Community 5`, `Community 6`, `Community 10`?**
  _High betweenness centrality (0.171) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `Chatboks` (e.g. with `AgentZeroAgent` and `Chatboks`) actually correct?**
  _`Chatboks` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `ContextBuilder` (e.g. with `AgentTimeoutError` and `AgentZeroAgent`) actually correct?**
  _`ContextBuilder` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Stream` (e.g. with `AgentTimeoutError` and `Any`) actually correct?**
  _`Stream` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `AgentZeroAgent` (e.g. with `BaseAgent` and `AgentZeroAgent`) actually correct?**
  _`AgentZeroAgent` has 12 INFERRED edges - model-reasoned connections that need verification._