"""Smoke tests for native ChatBoks skill discovery."""
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


def test_skills_command_lists_native_skills_without_agent_round() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/skills")

        message = app.stream.system.call_args.args[0]
        assert "Native ChatBoks skills:" in message
        assert "implement" in message
        assert "bugsearch" in message
        app.run_agent_round.assert_not_called()
        print("PASS: /skills lists native skills without routing to agents")


def test_skills_command_previews_requested_skill() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/skills implement")

        message = app.stream.system.call_args.args[0]
        assert "# Implement Mode" in message
        assert "Context Priming" in message
        assert "Quality Gate" in message
        print("PASS: /skills <name> previews a skill")


def test_skill_summary_prefers_summary_field() -> None:
    summary = Chatboks.skill_summary("# Example\n\nSummary: Use this one.\n\nBody")

    assert summary == "Use this one."
    print("PASS: skill summary uses Summary field")


if __name__ == "__main__":
    test_skills_command_lists_native_skills_without_agent_round()
    test_skills_command_previews_requested_skill()
    test_skill_summary_prefers_summary_field()
    print("\nAll skill smoke tests passed.")
