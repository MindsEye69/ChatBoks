"""Smoke test: PROPOSAL from non-last agent is buffered; all agents run before user is asked."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_app():
    """Return a Chatboks instance with all I/O mocked out."""
    config = {
        "projects": {
            "test": {
                "path": str(Path.home()),
                "agents": ["claude", "codex"],
            }
        },
        "agents": {
            "claude": {"token_warning": 100_000},
            "codex": {"token_warning": 100_000},
        },
        "rounds": {"max_before_escalate": 3},
        "context": {"max_token_recovery_retries": 0},
    }

    with patch("orchestrator.yaml.safe_load", return_value=config), \
         patch("orchestrator.Path.exists", return_value=True), \
         patch("orchestrator.Stream"), \
         patch("orchestrator.Router"), \
         patch("orchestrator.ContextBuilder"), \
         patch.object(Path, "read_text", return_value="{}"), \
         patch("orchestrator.json.loads", return_value={}):
        from orchestrator import Chatboks
        app = Chatboks.__new__(Chatboks)
        app.project = "test"
        app.trigger = "manual"
        app.config = config
        app.proj_config = config["projects"]["test"]
        app.proj_path = Path.home()
        app.chatboks_md = Path.home() / "chatboks.md"
        app.state_file = Path.home() / ".chatboks" / "state.json"
        app.stream = MagicMock()
        app.router = MagicMock()
        app.context = MagicMock()
        app._internal_write = False
        app.input_buffer = []
        app.state = {
            "round": 0,
            "round_intent": "respond",
            "expected_agents": [],
            "completed_agents": [],
            "proposal": None,
            "context": {"token_counts": {}},
            "status": "active",
        }
        return app


def test_proposal_buffered_until_all_agents_complete():
    """First agent PROPOSAL must not short-circuit; second agent must still run."""
    app = _make_app()

    call_log: list[str] = []

    def fake_call(agent_name: str, mode: str) -> str:
        call_log.append(agent_name)
        if agent_name == "claude":
            return "I suggest we do X.\n>>> PROPOSAL"
        # codex emits no controlling signal; it has reviewed the proposal in the transcript
        return "Agreed with claude's approach. No counter-proposal."

    app.call_agent_with_token_recovery = fake_call  # type: ignore[method-assign]
    app.append_message = MagicMock()
    app.update_token_count = MagicMock()
    app.mark_agent_completed = MagicMock()
    app.update_state = MagicMock()
    app.save_state = MagicMock()
    app.handle_proposal = MagicMock()
    app.all_expected_agents_completed = MagicMock(return_value=True)

    app.run_agent_round()

    # Both agents ran
    assert call_log == ["claude", "codex"], f"Expected both agents to run, got: {call_log}"

    # handle_proposal was called exactly once with claude's response
    app.handle_proposal.assert_called_once()
    response_arg, by_arg = app.handle_proposal.call_args.args
    assert "PROPOSAL" in response_arg
    assert by_arg == "claude"

    print("PASS: proposal buffered, both agents ran, handle_proposal called post-loop")


def test_single_agent_proposal_still_fires():
    """Single-agent project: PROPOSAL fires in post-loop handler (unchanged behavior)."""
    app = _make_app()
    app.proj_config = {**app.proj_config, "agents": ["claude"]}

    def fake_call(agent_name: str, mode: str) -> str:
        return "My suggestion.\n>>> PROPOSAL"

    app.call_agent_with_token_recovery = fake_call  # type: ignore[method-assign]
    app.append_message = MagicMock()
    app.update_token_count = MagicMock()
    app.mark_agent_completed = MagicMock()
    app.update_state = MagicMock()
    app.save_state = MagicMock()
    app.handle_proposal = MagicMock()
    app.all_expected_agents_completed = MagicMock(return_value=True)

    app.run_agent_round()

    app.handle_proposal.assert_called_once()
    print("PASS: single-agent PROPOSAL still triggers handle_proposal")


def test_question_after_proposal_abandons_buffer():
    """QUESTION from second agent returns immediately, abandoning buffered PROPOSAL."""
    app = _make_app()

    def fake_call(agent_name: str, mode: str) -> str:
        if agent_name == "claude":
            return "Proposal here.\n>>> PROPOSAL"
        return "Wait, what does X mean?\n>>> QUESTION"

    app.call_agent_with_token_recovery = fake_call  # type: ignore[method-assign]
    app.append_message = MagicMock()
    app.update_token_count = MagicMock()
    app.mark_agent_completed = MagicMock()
    app.update_state = MagicMock()
    app.save_state = MagicMock()
    app.handle_proposal = MagicMock()
    app.handle_question = MagicMock()
    app.all_expected_agents_completed = MagicMock(return_value=True)

    app.run_agent_round()

    # QUESTION returns immediately; handle_proposal must NOT be called
    app.handle_question.assert_called_once()
    app.handle_proposal.assert_not_called()
    print("PASS: QUESTION after PROPOSAL abandons buffered proposal")


def test_blocked_after_prior_completion_is_warning_not_terminal_block():
    """A weak trailing agent must not override a prior completed result."""
    app = _make_app()
    app.proj_config = {**app.proj_config, "agents": ["claude", "coordinator"]}

    def fake_call(agent_name: str, mode: str) -> str:
        if agent_name == "claude":
            return "Committed and pushed with evidence.\n>>> TASK_COMPLETE"
        return "Coordinator returned a bare control signal.\n>>> BLOCKED"

    app.call_agent_with_token_recovery = fake_call  # type: ignore[method-assign]
    app.append_message = MagicMock()
    app.update_token_count = MagicMock()
    app.mark_agent_completed = MagicMock()
    app.update_state = MagicMock()
    app.save_state = MagicMock()
    app.maybe_announce_direct_standby_agents = MagicMock()

    app.run_agent_round()

    app.stream.system.assert_any_call("coordinator blocked after claude completed the task; treating as a warning.")
    app.stream.system.assert_any_call("Task complete. Awaiting next instruction.")
    app.update_state.assert_any_call({"status": "idle", "active_task": None, "confirmation": None})
    assert all(
        call.args[0].get("status") != "blocked"
        for call in app.update_state.call_args_list
        if call.args and isinstance(call.args[0], dict)
    )
    print("PASS: trailing BLOCKED after prior completion is downgraded to warning")


if __name__ == "__main__":
    test_proposal_buffered_until_all_agents_complete()
    test_single_agent_proposal_still_fires()
    test_question_after_proposal_abandons_buffer()
    test_blocked_after_prior_completion_is_warning_not_terminal_block()
    print("\nAll smoke tests passed.")
