"""Smoke tests for agent availability and exhausted-agent routing."""
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
    app.config = {
        "projects": {
            "test": {
                "path": str(root),
                "agents": ["claude", "codex"],
                "primary": "claude",
            }
        },
        "agents": {
            "claude": {},
            "codex": {},
            "agent_zero": {},
        },
    }
    app.proj_config = app.config["projects"]["test"]
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.stream = MagicMock()
    app.router = MagicMock()
    app.router.primary.return_value = "claude"
    app.router.route_user_prompt.side_effect = lambda text: (
        (["claude"], text.removeprefix("@claude").strip(), "claude")
        if text.startswith("@claude")
        else (["claude", "codex"], text, None)
    )
    app.context = MagicMock()
    app._internal_write = False
    app.input_buffer = []
    app.state = Chatboks.normalize_state(
        app,
        {
            "session": "test",
            "round": 0,
            "status": "active",
            "context": {"token_counts": {}},
        },
    )
    app.save_state = MagicMock()
    return app


def test_agent_command_marks_exhausted_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/agent claude exhausted 50m")

        statuses = app.load_agent_statuses()
        assert statuses["claude"]["status"] == "exhausted"
        assert statuses["claude"].get("until")
        app.run_agent_round.assert_not_called()
        print("PASS: /agent marks exhausted without routing to agents")


def test_normal_round_substitutes_exhausted_agent():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.save_agent_statuses({"claude": {"status": "exhausted", "updated_at": app.timestamp()}})
        app.run_agent_round = MagicMock()

        app.handle_user_input("please inspect this")

        app.run_agent_round.assert_called_once()
        _, kwargs = app.run_agent_round.call_args
        assert kwargs["agents"] == ["codex"]
        assert app.state["next_agent"] == "codex"
        print("PASS: normal route substitutes exhausted agent")


def test_explicit_route_to_exhausted_agent_does_not_substitute():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.save_agent_statuses({"claude": {"status": "exhausted", "updated_at": app.timestamp()}})
        app.run_agent_round = MagicMock()

        app.handle_user_input("@claude please inspect this")

        app.run_agent_round.assert_not_called()
        message = app.stream.system.call_args.args[0]
        assert "claude is exhausted" in message.lower()
        print("PASS: explicit exhausted route asks user to override")


if __name__ == "__main__":
    test_agent_command_marks_exhausted_without_agent_round()
    test_normal_round_substitutes_exhausted_agent()
    test_explicit_route_to_exhausted_agent_does_not_substitute()
    print("\nAll agent status smoke tests passed.")
