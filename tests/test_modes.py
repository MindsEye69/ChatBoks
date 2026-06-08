"""Smoke tests for ChatBoks collaboration modes."""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context.builder import ContextBuilder
from orchestrator import COLLABORATION_MODES, Chatboks
from router import RoutingDecision


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


if __name__ == "__main__":
    test_mode_command_updates_state_without_agent_round()
    test_mode_status_lists_available_modes()
    test_round_context_includes_mode_instruction()
    test_handle_user_input_records_first_role_routed_agent_as_next()
    test_handle_user_input_records_mode_strategy_agent_as_next()
    print("\nAll mode smoke tests passed.")
