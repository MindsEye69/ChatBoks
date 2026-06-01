"""Regression tests for signal parsing and proposal state cleanup."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent_zero import AgentZeroAgent
from orchestrator import Chatboks


def _make_app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = {"agents": {"codex": {}}}
    app.proj_config = {"agents": ["codex"]}
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
            "proposal": {"id": "prop_old"},
            "context": {"token_counts": {"codex": 100_000}},
        },
    )
    app.save_state = MagicMock()
    return app


def test_parse_signal_uses_declared_priority():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        signal = app.parse_signal("Done.\n>>> BLOCKED\nActually done.\n>>> TASK_COMPLETE")

        assert signal == "TASK_COMPLETE"


def test_execute_proposal_clears_active_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.primary.return_value = "codex"
        app.call_agent_with_token_recovery = MagicMock(return_value="Applied.\n>>> TASK_COMPLETE")
        app.append_message = MagicMock()

        app.execute_proposal()

        assert app.state["status"] == "idle"
        assert app.state["proposal"] is None


def test_check_token_limit_uses_default_warning_threshold():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.recover_token_exhaustion = MagicMock()

        app.check_token_limit("codex")

        app.recover_token_exhaustion.assert_called_once()


def test_handle_approval_accepts_common_affirmatives():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.router.primary.return_value = "codex"
        app.execute_proposal = MagicMock()
        app.run_agent_round = MagicMock()

        app.handle_approval("yes")

        assert app.state["status"] == "executing"
        app.execute_proposal.assert_called_once()
        app.run_agent_round.assert_not_called()


def test_dismiss_command_clears_active_proposal_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/DISMISS")

        assert app.state["proposal"] is None
        assert app.state["status"] == "idle"
        assert app.state["next_agent"] == "you"
        app.run_agent_round.assert_not_called()


def test_agent_zero_strips_prefixed_signal_lines_from_body():
    agent = AgentZeroAgent.__new__(AgentZeroAgent)
    agent.name = "agent_zero"
    agent.signals = ("TASK_COMPLETE", "QUESTION", "BLOCKED")

    normalized = agent.normalize_output(">>> QUESTION\nWhat target?\n>>> QUESTION")

    assert normalized == "What target?\n>>> QUESTION"


if __name__ == "__main__":
    test_parse_signal_uses_declared_priority()
    test_execute_proposal_clears_active_proposal()
    test_check_token_limit_uses_default_warning_threshold()
    test_handle_approval_accepts_common_affirmatives()
    test_dismiss_command_clears_active_proposal_without_agent_round()
    test_agent_zero_strips_prefixed_signal_lines_from_body()
    print("All signal/state smoke tests passed.")
