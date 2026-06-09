from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.base import AgentTimeoutError
from orchestrator import Chatboks
from router import Router


class FakeAgent:
    cli = "claude"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def run_cli_once(self, prompt: str, command: list[str], **_kwargs: object) -> str:
        self.calls.append((prompt, command))
        return "review output"


class TimeoutAgent:
    cli = "claude"

    def run_cli_once(self, prompt: str, command: list[str], **_kwargs: object) -> str:
        raise AgentTimeoutError("claude", "idle", 300, partial_output="partial review")


def _make_app(root: Path) -> Chatboks:
    config = {
        "projects": {
            "test": {
                "path": str(root),
                "agents": ["claude", "codex"],
                "primary": "codex",
            }
        },
        "agents": {
            "claude": {
                "cli": "claude",
                "model_commands": [
                    {
                        "name": "ultrareview",
                        "aliases": ["/ultrareview", "ultrareview"],
                        "type": "cli_subcommand",
                        "argv": ["ultrareview", "{args}"],
                        "description": "Run Claude Ultrareview.",
                    }
                ],
            },
            "codex": {"cli": "codex"},
        },
        "context": {},
    }
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = config
    app.proj_config = config["projects"]["test"]
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.stream = MagicMock()
    app.router = Router(config, "test", root)
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
    app.append_message = MagicMock()
    app.run_agent_round = MagicMock()
    return app


def test_registered_model_command_executes_for_owner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        fake_agent = FakeAgent()
        app.router.get_agent = MagicMock(return_value=fake_agent)

        app.handle_user_input("@claude /ultrareview main --focus security")

        assert fake_agent.calls == [
            ("", ["claude", "ultrareview", "main", "--focus", "security"])
        ]
        app.run_agent_round.assert_not_called()
        app.append_message.assert_any_call("claude", "review output\n>>> TASK_COMPLETE")


def test_model_command_timeout_preserves_partial_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.get_agent = MagicMock(return_value=TimeoutAgent())

        app.handle_user_input("@claude /ultrareview main")

        app.run_agent_round.assert_not_called()
        response = next(call.args[1] for call in app.append_message.call_args_list if call.args[0] == "claude")
        assert "partial review" in response
        assert "CLI call idle timed out for claude after 300 seconds." in response
        assert ">>> BLOCKED" in response


def test_wrong_model_command_owner_gets_hint_and_discussion_round() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("@codex /ultrareview main")

        system_messages = [call.args[1] for call in app.append_message.call_args_list if call.args[0] == "system"]
        assert any("belongs to claude, not codex" in message for message in system_messages)
        app.run_agent_round.assert_called_once()
        _, kwargs = app.run_agent_round.call_args
        assert kwargs["agents"] == ["codex"]
        assert "[MODEL COMMAND NOTE]" in kwargs["initiator"]


def test_model_command_escape_forces_plain_prompt_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.get_agent = MagicMock()

        app.handle_user_input("@claude -- /ultrareview main")

        app.router.get_agent.assert_not_called()
        app.run_agent_round.assert_called_once()
        _, kwargs = app.run_agent_round.call_args
        assert kwargs["agents"] == ["claude"]
        assert kwargs["initiator"] == "/ultrareview main"


def test_unknown_model_slash_command_is_forwarded_as_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("@claude /unknown-command explain")

        app.run_agent_round.assert_called_once()
        _, kwargs = app.run_agent_round.call_args
        assert kwargs["agents"] == ["claude"]
        assert kwargs["initiator"] == "/unknown-command explain"


def test_raw_model_slash_command_stays_chatboks_local() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/ultrareview main")

        app.run_agent_round.assert_not_called()
        app.stream.system.assert_called_once()
        assert "Unknown local command" in app.stream.system.call_args.args[0]


def test_model_commands_command_lists_registered_commands() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/model-commands")

        app.stream.system.assert_called_once()
        output = app.stream.system.call_args.args[0]
        assert "Registered model commands:" in output
        assert "claude: ultrareview" in output


if __name__ == "__main__":
    test_registered_model_command_executes_for_owner()
    test_model_command_timeout_preserves_partial_output()
    test_wrong_model_command_owner_gets_hint_and_discussion_round()
    test_model_command_escape_forces_plain_prompt_text()
    test_unknown_model_slash_command_is_forwarded_as_text()
    test_raw_model_slash_command_stays_chatboks_local()
    test_model_commands_command_lists_registered_commands()
    print("All model command tests passed.")
