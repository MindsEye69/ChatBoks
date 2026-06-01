"""Smoke tests: slash commands bypass buffer_or_complete_input."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import Chatboks


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
            "round": 1,
            "status": "active",
            "context": {"token_counts": {}},
        },
    )
    app.save_state = MagicMock()
    return app


def test_slash_commands_bypass_buffer():
    """All known slash commands return immediately without buffering."""
    cases = [
        "/help",
        "/mode bugsearch",
        "/agent codex exhausted 60m",
        "/wins",
        "/unknowncommand",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        for cmd in cases:
            result = app.buffer_or_complete_input(cmd)
            assert result == cmd, f"Expected {cmd!r} to pass through, got {result!r}"
            assert app.input_buffer == [], f"Buffer should be empty after slash command, got {app.input_buffer}"
    print("PASS: slash commands bypass buffering")


def test_slash_command_does_not_clear_pending_buffer():
    """A slash command typed mid-composition leaves the existing buffer intact."""
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.input_buffer = ["I need to fix"]
        result = app.buffer_or_complete_input("/help")
        assert result == "/help"
        assert app.input_buffer == ["I need to fix"], "Buffer should survive a slash command"
    print("PASS: slash command does not clear pending buffer")


def test_plain_text_without_punctuation_is_buffered():
    """Non-slash text without terminal punctuation is buffered as before."""
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        result = app.buffer_or_complete_input("fix the bug in router")
        assert result is None
        assert app.input_buffer == ["fix the bug in router"]
    print("PASS: plain text without punctuation is buffered")


def test_handle_user_input_routes_slash_commands_without_buffer():
    """handle_user_input executes slash local commands end-to-end."""
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        # /help should render help box and not trigger a round
        app.handle_user_input("/help")
        app.stream.help_box.assert_called_once()
        app.run_agent_round.assert_not_called()

        # /wins should call show_outcomes and not trigger a round
        app.show_outcomes = MagicMock()
        app.handle_user_input("/wins")
        app.show_outcomes.assert_called_once()
        app.run_agent_round.assert_not_called()
    print("PASS: handle_user_input routes /help and /wins without agent round")


if __name__ == "__main__":
    test_slash_commands_bypass_buffer()
    test_slash_command_does_not_clear_pending_buffer()
    test_plain_text_without_punctuation_is_buffered()
    test_handle_user_input_routes_slash_commands_without_buffer()
    print("\nAll slash buffering smoke tests passed.")
