"""Smoke tests for ChatBoks collaboration modes."""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context.builder import ContextBuilder
from orchestrator import COLLABORATION_MODES, Chatboks


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


if __name__ == "__main__":
    test_mode_command_updates_state_without_agent_round()
    test_mode_status_lists_available_modes()
    test_round_context_includes_mode_instruction()
    print("\nAll mode smoke tests passed.")
