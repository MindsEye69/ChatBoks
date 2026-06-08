"""Regression tests for signal parsing and proposal state cleanup."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent_zero import AgentZeroAgent
from agents.base import AgentTimeoutError
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


def test_handle_proposal_includes_execution_cost_estimate_when_configured():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {
                "codex": {
                    "cost_per_million_input_tokens": 1.5,
                    "cost_per_million_output_tokens": 6.0,
                    "estimated_execute_output_tokens": 2000,
                }
            }
        }
        app.router.primary.return_value = "codex"
        app.context.build.return_value = "A" * 4000
        fake_agent = MagicMock()
        fake_agent.build_prompt.return_value = "B" * 8000
        app.router.get_agent.return_value = fake_agent

        app.handle_proposal("Ship it.\n>>> PROPOSAL", "codex")

        gate_text = app.stream.proposal.call_args.args[0]
        assert "Proposal from codex:" in gate_text
        assert "Estimated execution via codex:" in gate_text
        assert "Estimated cost: $" in gate_text
        assert app.state["proposal"]["execution_estimate"]["cost_configured"] is True


def test_handle_proposal_marks_cost_unavailable_when_rates_missing():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {"agents": {"codex": {}}}
        app.router.primary.return_value = "codex"
        app.context.build.return_value = "A" * 1200
        fake_agent = MagicMock()
        fake_agent.build_prompt.return_value = "B" * 2400
        app.router.get_agent.return_value = fake_agent

        app.handle_proposal("Ship it.\n>>> PROPOSAL", "codex")

        gate_text = app.stream.proposal.call_args.args[0]
        assert "Estimated cost: unavailable" in gate_text
        assert app.state["proposal"]["execution_estimate"]["cost_configured"] is False


def test_check_token_limit_uses_default_warning_threshold():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.recover_token_exhaustion = MagicMock()

        app.check_token_limit("codex")

        app.recover_token_exhaustion.assert_called_once()


def test_update_token_count_refreshes_session_token_display():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"codex": {"token_limit": 120_000, "token_warning": 100_000}},
            "context": {"session_token_budget_warning": 220_000, "session_token_budget_limit": 280_000},
        }

        app.update_token_count("codex", "x" * 40)

        assert app.state["context"]["token_counts"]["codex"] == 100_010
        app.stream.token_usage.assert_called_once_with(
            app.state["context"]["token_counts"],
            {"used": 100_010, "warning": 220_000, "limit": 280_000, "agent_count": 1},
        )


def test_session_token_budget_emits_warning_once():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {"context": {"session_token_budget_warning": 90_000, "session_token_budget_limit": 150_000}}
        app.state["context"]["session_budget_warning_emitted"] = False

        allowed = app.ensure_session_token_budget()

        assert allowed
        assert app.state["context"]["session_budget_warning_emitted"] is True
        app.stream.system.assert_called_once()


def test_session_token_budget_blocks_new_work_at_hard_cap():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {"context": {"session_token_budget_warning": 90_000, "session_token_budget_limit": 100_000}}
        app.run_agent_round = MagicMock()

        app.handle_user_input("proceed")

        assert app.state["status"] == "blocked"
        assert app.stream.system.call_count >= 1
        app.run_agent_round.assert_not_called()


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


def test_load_state_accepts_utf8_bom():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.state_file.parent.mkdir(parents=True, exist_ok=True)
        app.state_file.write_text(
            '{"session": "test", "round": 2, "status": "idle"}',
            encoding="utf-8-sig",
        )

        state = app.load_state()

        assert state["status"] == "idle"
        assert state["round"] == 2


def test_agent_zero_strips_prefixed_signal_lines_from_body():
    agent = AgentZeroAgent.__new__(AgentZeroAgent)
    agent.name = "agent_zero"
    agent.signals = ("TASK_COMPLETE", "QUESTION", "BLOCKED")

    normalized = agent.normalize_output(">>> QUESTION\nWhat target?\n>>> QUESTION")

    assert normalized == "What target?\n>>> QUESTION"


def test_agent_timeout_recovery_checkpoints_partial_output_and_retries():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"codex": {"token_warning": 100_000}},
            "context": {"max_token_recovery_retries": 0, "max_timeout_recovery_retries": 1},
        }
        app.state["context"]["token_counts"]["codex"] = 0
        app.context.build.return_value = "context"

        agent = MagicMock()
        agent.call.side_effect = [
            AgentTimeoutError("codex", "idle", 300, partial_output="draft patch notes"),
            "Recovered.\n>>> TASK_COMPLETE",
        ]
        app.router.get_agent.return_value = agent

        response = app.call_agent_with_token_recovery("codex", mode="respond")

        assert response == "Recovered.\n>>> TASK_COMPLETE"
        assert agent.call.call_count == 2
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        assert ">>> TIMEOUT_CHECKPOINT" in transcript
        assert "draft patch notes" in transcript
        assert ">>> TIMEOUT_RECOVERY" in transcript


def test_agent_timeout_recovery_blocks_after_retry_budget():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"codex": {"token_warning": 100_000}},
            "context": {"max_token_recovery_retries": 0, "max_timeout_recovery_retries": 0},
        }
        app.state["context"]["token_counts"]["codex"] = 0
        app.context.build.return_value = "context"

        agent = MagicMock()
        agent.call.side_effect = AgentTimeoutError(
            "codex",
            "idle",
            300,
            partial_output="unfinished analysis",
        )
        app.router.get_agent.return_value = agent

        response = app.call_agent_with_token_recovery("codex", mode="respond")

        assert "codex timed out and automatic recovery did not complete." in response
        assert ">>> BLOCKED" in response
        assert agent.call.call_count == 1
        assert "unfinished analysis" in app.chatboks_md.read_text(encoding="utf-8")


def test_agent_timeout_loop_detection_uses_changed_line_overlap():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {"context": {"timeout_loop_overlap_threshold": 0.8}}
        previous = "\n".join(
            [
                "diff --git a/a.py b/a.py",
                "--- a/a.py",
                "+++ b/a.py",
                "-old line",
                "+new line",
                "+kept line",
            ]
        )
        current = "\n".join(
            [
                "diff --git a/a.py b/a.py",
                "--- a/a.py",
                "+++ b/a.py",
                "+new line",
                "+kept line",
            ]
        )

        assert app.agent_timeout_is_looping(current, [previous])
        assert not app.agent_timeout_is_looping("+different line", [previous])


def test_agent_timeout_recovery_blocks_when_git_diff_repeats():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"codex": {"token_warning": 100_000}},
            "context": {
                "max_token_recovery_retries": 0,
                "max_timeout_recovery_retries": 2,
                "timeout_loop_overlap_threshold": 0.8,
            },
        }
        app.state["context"]["token_counts"]["codex"] = 0
        app.context.build.return_value = "context"
        app.capture_git_diff = MagicMock(
            return_value="\n".join(
                [
                    "diff --git a/orchestrator.py b/orchestrator.py",
                    "--- a/orchestrator.py",
                    "+++ b/orchestrator.py",
                    "+same attempted patch",
                ]
            )
        )

        agent = MagicMock()
        agent.call.side_effect = [
            AgentTimeoutError("codex", "idle", 300, partial_output="attempt one"),
            AgentTimeoutError("codex", "idle", 300, partial_output="attempt two"),
            "Should not be reached.\n>>> TASK_COMPLETE",
        ]
        app.router.get_agent.return_value = agent

        response = app.call_agent_with_token_recovery("codex", mode="respond")

        assert "codex appears to be looping during timeout recovery." in response
        assert ">>> BLOCKED" in response
        assert agent.call.call_count == 2
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        assert ">>> TIMEOUT_RECOVERY" in transcript
        assert ">>> LOOP_DETECTED" in transcript


if __name__ == "__main__":
    test_parse_signal_uses_declared_priority()
    test_execute_proposal_clears_active_proposal()
    test_handle_proposal_includes_execution_cost_estimate_when_configured()
    test_handle_proposal_marks_cost_unavailable_when_rates_missing()
    test_check_token_limit_uses_default_warning_threshold()
    test_handle_approval_accepts_common_affirmatives()
    test_dismiss_command_clears_active_proposal_without_agent_round()
    test_load_state_accepts_utf8_bom()
    test_agent_zero_strips_prefixed_signal_lines_from_body()
    test_agent_timeout_recovery_checkpoints_partial_output_and_retries()
    test_agent_timeout_recovery_blocks_after_retry_budget()
    test_agent_timeout_loop_detection_uses_changed_line_overlap()
    test_agent_timeout_recovery_blocks_when_git_diff_repeats()
    print("All signal/state smoke tests passed.")
