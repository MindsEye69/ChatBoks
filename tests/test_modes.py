"""Smoke tests for ChatBoks collaboration modes."""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context.builder import ContextBuilder
from orchestrator import COLLABORATION_MODES, Chatboks
from router import Router, RoutingDecision


def _make_app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = {}
    app.proj_config = {"agents": ["claude", "codex"]}
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.stream = MagicMock()
    app.router = MagicMock()
    app.context = MagicMock()
    app._internal_write = False
    app.input_buffer = []
    app.state = Chatboks.normalize_state(
        app,
        {
            "session": "test",
            "round": 3,
            "status": "active",
            "context": {"token_counts": {}},
        },
    )
    app.save_state = MagicMock()
    return app


def test_mode_command_updates_state_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/mode bugsearch")

        assert app.state["collaboration_mode"] == "bugsearch"
        assert app.state["collaboration_mode_instruction"] == COLLABORATION_MODES["bugsearch"]
        app.run_agent_round.assert_not_called()
        print("PASS: /mode updates state without routing to agents")


def test_mode_status_lists_available_modes():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/mode")

        message = app.stream.system.call_args.args[0]
        assert "Current mode: default" in message
        assert "brainstorm" in message
        assert "bugsearch" in message
        print("PASS: /mode lists current and available modes")


def test_round_context_includes_mode_instruction():
    builder = ContextBuilder(Path("."), {})
    state = {
        "round_intent": "respond",
        "collaboration_mode": "review",
        "collaboration_mode_instruction": COLLABORATION_MODES["review"],
        "expected_agents": ["claude", "codex"],
        "completed_agents": ["claude"],
        "next_agent": "codex",
    }

    context = builder.load_round_context(state)

    assert "Collaboration mode: review" in context
    assert COLLABORATION_MODES["review"] in context
    print("PASS: round context includes collaboration mode")


def test_start_resumes_pending_handoff_before_input_loop():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.state["status"] = "handoff"
        app.ensure_project_files = MagicMock()
        app.refresh_token_usage_display = MagicMock()
        app.handle_handoff = MagicMock(side_effect=lambda: app.state.update({"status": "idle"}))
        app.run_input_loop = MagicMock()

        app.start()

        app.stream.system.assert_any_call("Pending handoff detected.")
        app.handle_handoff.assert_called_once()
        app.run_input_loop.assert_called_once()
        print("PASS: startup resumes pending handoff before entering input loop")


def test_start_once_resumes_pending_handoff_without_extra_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.state["status"] = "handoff"
        app.ensure_project_files = MagicMock()
        app.refresh_token_usage_display = MagicMock()
        app.handle_handoff = MagicMock(side_effect=lambda: app.state.update({"status": "idle"}))
        app.run_agent_round = MagicMock()

        app.start(once=True)

        app.handle_handoff.assert_called_once()
        app.run_agent_round.assert_not_called()
        print("PASS: once startup resumes handoff without launching an unrelated round")


def test_handle_user_input_records_first_role_routed_agent_as_next():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.state["collaboration_mode"] = "implement"
        app.router.route_user_prompt_details.return_value = RoutingDecision(
            ["codex", "claude"],
            "patch the router",
        )
        app.resolve_available_agents = MagicMock(return_value=["codex", "claude"])
        app.run_agent_round = MagicMock()

        app.handle_user_input("patch the router")

        app.router.route_user_prompt_details.assert_called_once_with(
            "patch the router",
            collaboration_mode="implement",
        )
        assert app.state["next_agent"] == "codex"
        assert app.state["active_task"] == "patch the router"
        app.run_agent_round.assert_called_once_with(
            initiator="patch the router",
            agents=["codex", "claude"],
        )
        print("PASS: role-routed rounds store the first routed agent as next")


def test_handle_user_input_records_mode_strategy_agent_as_next():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.state["collaboration_mode"] = "review"
        app.router.route_user_prompt_details.return_value = RoutingDecision(
            ["claude"],
            "review the fallback path",
            note="Mode strategy: review routes this request to Claude first.",
            strategy="mode_solo_claude",
        )
        app.resolve_available_agents = MagicMock(return_value=["claude"])
        app.run_agent_round = MagicMock()

        app.handle_user_input("review the fallback path")

        assert app.state["next_agent"] == "claude"
        assert app.state["active_task"] == "review the fallback path"
        app.run_agent_round.assert_called_once_with(
            initiator="review the fallback path",
            agents=["claude"],
        )
        print("PASS: mode strategy rounds store the routed solo agent as next")


def test_broad_multi_agent_prompt_triggers_criteria_gate():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.route_user_prompt_details.return_value = RoutingDecision(
            ["claude", "codex"],
            "all agents give your top improvements, do three rounds",
            strategy="explicit_all",
        )
        app.resolve_available_agents = MagicMock(return_value=["claude", "codex"])
        app.run_agent_round = MagicMock()

        app.handle_user_input("@all give your top improvements, do three rounds")

        assert app.state["status"] == "awaiting_criteria"
        assert app.state["next_agent"] == "you"
        assert app.state["criteria_gate"]["agents"] == ["claude", "codex"]
        assert "multi_agent" in app.state["criteria_gate"]["reasons"]
        assert "broad" in app.state["criteria_gate"]["reasons"]
        app.stream.proposal.assert_called_once()
        app.run_agent_round.assert_not_called()
        print("PASS: broad multi-agent prompts pause for criteria")


def test_criteria_approval_resumes_routed_prompt_without_rerouting():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.route_user_prompt_details.return_value = RoutingDecision(
            ["claude", "codex"],
            "all agents give your top improvements, do three rounds",
            strategy="explicit_all",
        )
        app.resolve_available_agents = MagicMock(return_value=["claude", "codex"])
        app.run_agent_round = MagicMock()

        app.handle_user_input("@all give your top improvements, do three rounds")
        app.handle_user_input("APPROVE")

        app.router.route_user_prompt_details.assert_called_once()
        assert app.state["status"] == "active"
        assert app.state["criteria_gate"] is None
        app.run_agent_round.assert_called_once_with(
            initiator="all agents give your top improvements, do three rounds",
            agents=["claude", "codex"],
        )
        print("PASS: criteria approval resumes the pending routed prompt")


def test_narrow_fix_prompt_bypasses_criteria_gate():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.route_user_prompt_details.return_value = RoutingDecision(
            ["codex"],
            "fix the typo in help text",
            strategy="single_agent_codex",
        )
        app.resolve_available_agents = MagicMock(return_value=["codex"])
        app.run_agent_round = MagicMock()

        app.handle_user_input("fix the typo in help text")

        assert app.state["status"] == "active"
        assert app.state.get("criteria_gate") is None
        app.run_agent_round.assert_called_once_with(
            initiator="fix the typo in help text",
            agents=["codex"],
        )
        print("PASS: narrow fixes bypass the criteria gate")


def test_router_confirmation_mode_strategy_routes_to_primary():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "test": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "primary": "codex",
                    "mode_strategies": {"confirmation": "confirm_round"},
                }
            },
            "agents": {"claude": {}, "codex": {}},
        }
        router = Router(config, "test", Path(tmp))

        decision = router.route_user_prompt_details("implement the thing", collaboration_mode="confirmation")

        assert decision.agents == ["codex"]
        assert decision.strategy == "mode_confirmation"
        assert "confirmation" in (decision.note or "")
        print("PASS: confirmation mode strategy routes to primary executor")


def test_confirmation_mode_verifies_completed_output():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_confirmation_repairs": 1},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.state["collaboration_mode"] = "confirmation"
        app.state["collaboration_mode_instruction"] = COLLABORATION_MODES["confirmation"]
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                "Implemented.\n>>> TASK_COMPLETE",
                "Confirmed complete.\n>>> TASK_COMPLETE",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        assert app.call_agent_with_token_recovery.call_args_list[0].args == ("codex",)
        assert app.call_agent_with_token_recovery.call_args_list[1].args == ("claude",)
        assert app.call_agent_with_token_recovery.call_count == 2
        assert app.state["status"] == "idle"
        assert app.state["active_task"] is None
        assert app.state["confirmation"] is None
        system_messages = [call.args[1] for call in app.append_message.call_args_list if call.args[0] == "system"]
        assert any("Confirmation mode:" in message for message in system_messages)
        app.stream.system.assert_any_call("Confirmation complete: claude verified codex's output.")
        print("PASS: confirmation mode verifies completed output")


def test_confirmation_mode_includes_packet_checklist_for_verifier():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_confirmation_repairs": 1},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.state["collaboration_mode"] = "confirmation"
        app.state["collaboration_mode_instruction"] = COLLABORATION_MODES["confirmation"]
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                (
                    "Implemented.\n"
                    ">>> PACKET\n"
                    "stance: ADD\n"
                    "observed:\n"
                    "- packet fact carried forward\n"
                    "risks:\n"
                    "- packet risk needs verifier attention\n"
                    "next_action: verifier checks risk\n"
                    "signal: TASK_COMPLETE\n"
                    ">>> PACKET_END\n"
                    ">>> TASK_COMPLETE"
                ),
                "Risk reviewed and accepted; confirmed complete.\n>>> TASK_COMPLETE",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        system_messages = [call.args[1] for call in app.append_message.call_args_list if call.args[0] == "system"]
        confirmation_prompt = next(message for message in system_messages if "Confirmation mode:" in message)
        assert "Executor Thought Packet checklist:" in confirmation_prompt
        assert "packet fact carried forward" in confirmation_prompt
        assert "packet risk needs verifier attention" in confirmation_prompt
        assert "verifier checks risk" in confirmation_prompt
        assert app.state["status"] == "idle"
        print("PASS: confirmation verifier prompt includes packet checklist")


def test_confirmation_mode_requires_packet_risks_to_be_addressed():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_confirmation_repairs": 1},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.state["collaboration_mode"] = "confirmation"
        app.state["collaboration_mode_instruction"] = COLLABORATION_MODES["confirmation"]
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                (
                    "Implemented.\n"
                    ">>> PACKET\n"
                    "stance: ADD\n"
                    "observed:\n"
                    "- implementation done\n"
                    "risks:\n"
                    "- focused test still missing\n"
                    "next_action: verifier checks risk\n"
                    "signal: TASK_COMPLETE\n"
                    ">>> PACKET_END\n"
                    ">>> TASK_COMPLETE"
                ),
                "Confirmed complete.\n>>> TASK_COMPLETE",
                "Added the focused test.\n>>> TASK_COMPLETE",
                "Confirmed after repair.\n>>> TASK_COMPLETE",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        called_agents = [call.args[0] for call in app.call_agent_with_token_recovery.call_args_list]
        assert called_agents == ["codex", "claude", "codex", "claude"]
        system_messages = [call.args[1] for call in app.append_message.call_args_list if call.args[0] == "system"]
        assert any("completion without addressing actionable executor packet risks" in message for message in system_messages)
        assert any("focused test still missing" in message for message in system_messages)
        assert app.state["confirmation_repairs_used"] == 1
        assert app.state["status"] == "idle"
        print("PASS: confirmation mode requires packet risks to be addressed")


def test_confirmation_mode_unresolved_risk_words_do_not_count_as_resolution():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        executor_response = (
            "Implemented.\n"
            ">>> PACKET\n"
            "stance: ADD\n"
            "observed:\n"
            "- implementation done\n"
            "risks:\n"
            "- focused test still missing\n"
            "next_action: verifier checks risk\n"
            "signal: TASK_COMPLETE\n"
            ">>> PACKET_END\n"
            ">>> TASK_COMPLETE"
        )

        unresolved = app.unresolved_packet_risks(
            executor_response,
            "Confirmed complete, but the focused test still missing risk remains unresolved.\n>>> TASK_COMPLETE",
            "codex",
        )
        accepted = app.unresolved_packet_risks(
            executor_response,
            "The focused test still missing risk is explicitly acknowledged and accepted.\n>>> TASK_COMPLETE",
            "codex",
        )

        assert unresolved == ["focused test still missing"]
        assert accepted == []
        print("PASS: unresolved risk wording does not satisfy packet-risk gate")


def test_confirmation_risk_local_smoke_command_does_not_call_agents():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/test confirmation-risk")

        app.run_agent_round.assert_not_called()
        app.stream.system.assert_called_once()
        message = app.stream.system.call_args.args[0]
        assert "Confirmation packet-risk local smoke:" in message
        assert "PASS: packet checklist includes observed fact" in message
        assert "PASS: bare verifier completion is rejected" in message
        assert "PASS: explicit verifier acknowledgement is accepted" in message
        assert "No agents called; no files edited." in message
        assert ">>> TASK_COMPLETE" in message
        print("PASS: /test confirmation-risk runs locally")


def test_confirmation_mode_returns_failed_check_to_executor_once():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_confirmation_repairs": 1},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.state["collaboration_mode"] = "confirmation"
        app.state["collaboration_mode_instruction"] = COLLABORATION_MODES["confirmation"]
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                "Implemented.\n>>> TASK_COMPLETE",
                "Missing a focused test.\n>>> HANDOFF",
                "Added the missing test.\n>>> TASK_COMPLETE",
                "Confirmed after repair.\n>>> TASK_COMPLETE",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        called_agents = [call.args[0] for call in app.call_agent_with_token_recovery.call_args_list]
        assert called_agents == ["codex", "claude", "codex", "claude"]
        assert app.state["confirmation_repairs_used"] == 1
        assert app.state["status"] == "idle"
        assert app.state["active_task"] is None
        app.stream.system.assert_any_call("Confirmation requested repair from codex; returning control to codex.")
        app.stream.system.assert_any_call("Confirmation complete: claude verified codex's output.")
        print("PASS: confirmation mode returns failed checks to executor once")


def test_confirmation_mode_executor_handoff_continues_to_verifier():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_confirmation_repairs": 1},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.state["collaboration_mode"] = "confirmation"
        app.state["collaboration_mode_instruction"] = COLLABORATION_MODES["confirmation"]
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                "Implemented and ready for review.\n>>> HANDOFF",
                "Verified the implementation.\n>>> TASK_COMPLETE",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        called_agents = [call.args[0] for call in app.call_agent_with_token_recovery.call_args_list]
        assert called_agents == ["codex", "claude"]
        assert app.state["status"] == "idle"
        assert app.state["active_task"] is None
        assert app.state["confirmation"] is None
        app.stream.system.assert_any_call("Confirmation complete: claude verified codex's output.")
        print("PASS: confirmation executor handoff continues to verifier")


def test_general_handoff_auto_continues_to_next_agent():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_handoff_depth": 3},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                "Implemented and handing to control.\n>>> HANDOFF",
                "Verified.\n>>> TASK_COMPLETE",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        called_agents = [call.args[0] for call in app.call_agent_with_token_recovery.call_args_list]
        assert called_agents == ["codex", "claude"]
        assert app.state["status"] == "idle"
        assert app.state["handoff_depth"] == 0
        app.stream.system.assert_any_call("Handoff queued for claude (depth 1/3).")
        print("PASS: general handoff auto-continues to the next agent")


def test_handoff_depth_limit_blocks_cycles():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_handoff_depth": 2},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                "Need control.\n>>> HANDOFF",
                "Returning for repair.\n>>> HANDOFF",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        called_agents = [call.args[0] for call in app.call_agent_with_token_recovery.call_args_list]
        assert called_agents == ["codex", "claude"]
        assert app.state["status"] == "blocked"
        assert app.state["blocked_reason"] == "handoff_deadlock"
        assert app.state["handoff_depth"] == 2
        app.stream.system.assert_any_call("Handoff deadlock: depth 2 reached without completion. Your input needed.")
        print("PASS: handoff depth limit blocks cycles")


def test_confirmation_mode_blocks_when_repair_budget_is_exhausted():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"claude": {}, "codex": {}},
            "rounds": {"max_before_escalate": 3, "max_confirmation_repairs": 0},
        }
        app.proj_config = {"agents": ["claude", "codex"], "primary": "codex"}
        app.state["collaboration_mode"] = "confirmation"
        app.state["collaboration_mode_instruction"] = COLLABORATION_MODES["confirmation"]
        app.append_message = MagicMock()
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                "Implemented.\n>>> TASK_COMPLETE",
                "Missing verification.\n>>> HANDOFF",
            ]
        )

        app.run_agent_round(initiator="implement the thing", agents=["codex"])

        assert app.call_agent_with_token_recovery.call_count == 2
        assert app.state["status"] == "blocked"
        assert app.state["next_agent"] == "you"
        assert app.state["confirmation"]["blocked_reason"] == "repair_budget_exhausted"
        app.stream.system.assert_any_call("Confirmation blocked: repair budget exhausted. Your input needed.")
        print("PASS: confirmation mode blocks when repair budget is exhausted")


if __name__ == "__main__":
    test_mode_command_updates_state_without_agent_round()
    test_mode_status_lists_available_modes()
    test_round_context_includes_mode_instruction()
    test_start_resumes_pending_handoff_before_input_loop()
    test_start_once_resumes_pending_handoff_without_extra_round()
    test_handle_user_input_records_first_role_routed_agent_as_next()
    test_handle_user_input_records_mode_strategy_agent_as_next()
    test_broad_multi_agent_prompt_triggers_criteria_gate()
    test_criteria_approval_resumes_routed_prompt_without_rerouting()
    test_narrow_fix_prompt_bypasses_criteria_gate()
    test_router_confirmation_mode_strategy_routes_to_primary()
    test_confirmation_mode_verifies_completed_output()
    test_confirmation_mode_includes_packet_checklist_for_verifier()
    test_confirmation_mode_requires_packet_risks_to_be_addressed()
    test_confirmation_mode_unresolved_risk_words_do_not_count_as_resolution()
    test_confirmation_risk_local_smoke_command_does_not_call_agents()
    test_confirmation_mode_returns_failed_check_to_executor_once()
    test_confirmation_mode_blocks_when_repair_budget_is_exhausted()
    test_general_handoff_auto_continues_to_next_agent()
    test_handoff_depth_limit_blocks_cycles()
    print("\nAll mode smoke tests passed.")
