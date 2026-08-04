"""Regression coverage for bounded, journaled peer consultations."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.claude import ClaudeAgent
from agents.codex import CodexAgent
from orchestrator import Chatboks


def _make_app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = {"agents": {"claude": {}, "codex": {}}, "rounds": {"max_before_escalate": 3}}
    app.proj_config = {"agents": ["claude", "codex"]}
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.stream = MagicMock()
    app.router = MagicMock()
    app.context = MagicMock()
    app.context.build.return_value = "[PROJECT CONTEXT] concise test context"
    app.context.summarize.return_value = ""
    app._internal_write = False
    app.input_buffer = []
    app.state = app.normalize_state(
        {
            "session": "test",
            "round": 1,
            "status": "active",
            "active_task": "Inspect peer consultation",
            "context": {"token_counts": {}},
        }
    )
    app.save_state = MagicMock()
    return app


def test_consult_mode_is_read_only_and_never_emits_control_lines():
    with tempfile.TemporaryDirectory() as tmp:
        agent = ClaudeAgent(Path(tmp), {"cli": "claude"}, "peer role")

        prompt = agent.build_prompt("[PEER CONSULTATION]", mode="consult")

        assert "read-only peer consultant" in prompt
        assert "Do not write, edit, move, or delete files" in prompt
        assert "Do not delegate, request another consultation" in prompt
        assert "emit ChatBoks >>> control lines" in prompt


def test_cli_peer_consultation_uses_the_safe_default_adapter_profile(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        claude = ClaudeAgent(root, {"cli": "claude"}, "peer role")
        codex = CodexAgent(root, {"cli": "codex"}, "peer role")
        commands: list[list[str]] = []

        def fake_run_cli_once(prompt, command, **kwargs):
            commands.append(command)
            return "peer response"

        monkeypatch.setattr(claude, "run_cli_once", fake_run_cli_once)
        monkeypatch.setattr(codex, "run_cli_once", fake_run_cli_once)

        assert claude.profile_for_mode("consult") == "claude_code_plan_v1"
        assert codex.profile_for_mode("consult") == "codex_exec_plan_v1"
        assert claude.call("context", mode="consult") == "peer response"
        assert codex.call("context", mode="consult") == "peer response"
        assert commands == [
            ["claude", "--print", "--permission-mode", "plan"],
            ["codex", "exec", "-C", str(root), "-s", "read-only", "-"],
        ]


def test_parse_agent_consult_request_requires_the_structured_block():
    valid = """Need a second opinion.
>>> CONSULT Claude
>>> CONSULT_REQUEST
Review the retry logic in agents/base.py for unsafe edge cases.
"""

    assert Chatboks.parse_agent_consult_request(valid) == (
        "claude",
        "Review the retry logic in agents/base.py for unsafe edge cases.",
    )
    assert Chatboks.parse_agent_consult_request(">>> CONSULT claude\nNeed a review") == ("claude", "")


def test_agent_consult_runs_peer_read_only_then_resumes_requester():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                """I need a review.\n>>> CONSULT claude\n>>> CONSULT_REQUEST\nReview `agents/base.py` for regressions.\n""",
                "The timeout path is safe; add a regression test.\n",
                "I will include the regression test.\n>>> TASK_COMPLETE",
            ]
        )
        app.append_message = MagicMock()
        app.update_token_count = MagicMock()
        app.confirm_completion_if_needed = MagicMock(return_value="confirmed")
        app.maybe_announce_direct_standby_agents = MagicMock()

        app.run_agent_round(initiator="Inspect peer consultation", agents=["codex"])

        calls = app.call_agent_with_token_recovery.call_args_list
        assert calls[0].args == ("codex",)
        assert calls[0].kwargs == {"mode": "respond"}
        assert calls[1].args == ("claude",)
        assert calls[1].kwargs["mode"] == "consult"
        assert "Review `agents/base.py` for regressions." in calls[1].kwargs["extra_context"]
        assert calls[2].args == ("codex",)
        assert calls[2].kwargs["mode"] == "respond"
        assert "The timeout path is safe" in calls[2].kwargs["extra_context"]
        assert app.state["consult_depth"] == 1
        assert app.state["consultation"] is None
        assert app.state["last_consultation"]["target"] == "claude"
        assert app.state["status"] == "idle"
        assert any(
            args == ("system", "[CONSULT REQUEST codex -> claude]\nReview `agents/base.py` for regressions.")
            for args, _kwargs in app.append_message.call_args_list
        )


def test_agent_consultation_depth_limit_blocks_recursive_ping_pong():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.call_agent_with_token_recovery = MagicMock(
            side_effect=[
                ">>> CONSULT claude\n>>> CONSULT_REQUEST\nReview the retry logic.",
                "The retry logic needs a cap.",
                ">>> CONSULT claude\n>>> CONSULT_REQUEST\nDouble-check the cap.",
            ]
        )
        app.append_message = MagicMock()
        app.update_token_count = MagicMock()

        app.run_agent_round(initiator="Inspect peer consultation", agents=["codex"])

        assert app.call_agent_with_token_recovery.call_count == 3
        assert app.state["consult_depth"] == 1
        assert app.state["status"] == "blocked"
        assert app.state["blocked_reason"] == "consultation"
        app.stream.system.assert_any_call(
            "Consultation denied for codex: Consultation depth limit reached (1/1); no additional peer call was run."
        )


def test_direct_consultation_is_journaled_and_bounded():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = _make_app(root)
        app.proj_config["consultation"] = {"max_response_chars": 10}
        app.call_agent_with_token_recovery = MagicMock(return_value="0123456789ABCDEF")
        app.update_token_count = MagicMock()

        app.handle_user_input("/consult claude review the current diff")

        call = app.call_agent_with_token_recovery.call_args
        assert call.args == ("claude",)
        assert call.kwargs["mode"] == "consult"
        assert "review the current diff" in call.kwargs["extra_context"]
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        journal = (root / ".chatboks" / "sessions" / "test" / "journal.md").read_text(encoding="utf-8")
        for text in (transcript, journal):
            assert "/consult claude review the current diff" in text
            assert "[CONSULT REQUEST you -> claude]" in text
            assert "0123456789" in text
            assert "ABCDEF" not in text
            assert "response was truncated to the configured limit" in text
        assert app.state["consultation"] is None
        assert app.state["last_consultation"]["response_truncated"] is True


def test_direct_consult_does_not_substitute_an_unavailable_peer():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = _make_app(root)
        app.agent_status_path().parent.mkdir(parents=True, exist_ok=True)
        app.agent_status_path().write_text('{"claude": {"status": "exhausted"}}', encoding="utf-8")
        app.call_agent_with_token_recovery = MagicMock()
        app.update_token_count = MagicMock()

        app.handle_user_input("/consult claude review the current diff")

        app.call_agent_with_token_recovery.assert_not_called()
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        assert "claude is exhausted or unavailable; the consultation was not run." in transcript
        assert app.state["last_consultation"]["status"] == "unavailable"
