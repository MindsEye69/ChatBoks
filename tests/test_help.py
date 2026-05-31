"""Smoke tests for the local /help command."""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import Chatboks, HELP_COMMANDS
from ui.stream import Stream


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


def test_help_command_renders_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/help")

        app.stream.help_box.assert_called_once_with(HELP_COMMANDS)
        app.run_agent_round.assert_not_called()
        print("PASS: /help renders locally without routing to agents")


def test_stream_help_box_contains_bbs_frame_and_commands():
    buffer = io.StringIO()
    stream = Stream({}, [])
    stream.console = Console(file=buffer, width=80, color_system=None)

    stream.help_box(HELP_COMMANDS)

    output = buffer.getvalue()
    assert "+-" in output
    assert "CHATBOKS COMMAND DECK" in output
    assert "/agent" in output
    assert "APPROVE / MODIFY / REJECT" in output
    print("PASS: help box renders command deck")


if __name__ == "__main__":
    test_help_command_renders_without_agent_round()
    test_stream_help_box_contains_bbs_frame_and_commands()
    print("\nAll help smoke tests passed.")
