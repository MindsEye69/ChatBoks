"""Smoke tests for manual collaboration outcome tracking."""
from __future__ import annotations

import json
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
    app.state = {
        "session": "test",
        "round": 7,
        "status": "active",
        "context": {"token_counts": {}},
    }
    app.save_state = MagicMock()
    return app


def test_win_command_records_jsonl_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input('/win codex missed_defect high "Caught the IPC pipe fallback."')

        records = app.load_outcomes()
        assert len(records) == 1
        assert records[0]["type"] == "win"
        assert records[0]["agent"] == "codex"
        assert records[0]["category"] == "missed_defect"
        assert records[0]["impact"] == "high"
        assert records[0]["round"] == 7
        assert records[0]["note"] == "Caught the IPC pipe fallback."
        app.run_agent_round.assert_not_called()
        print("PASS: /win records JSONL without routing to agents")


def test_outcomes_summary_reads_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.ensure_project_files()
        app.outcomes_path().write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-06-01T00:00:00",
                            "project": "test",
                            "round": 1,
                            "type": "win",
                            "agent": "claude",
                            "category": "better_architecture",
                            "impact": "medium",
                            "mode": "manual",
                            "note": "Found the simpler flow.",
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-06-01T00:01:00",
                            "project": "test",
                            "round": 2,
                            "type": "failure",
                            "agent": "agent_zero",
                            "category": "bad_signal",
                            "impact": "medium",
                            "mode": "manual",
                            "note": "Returned a bare QUESTION.",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        app.show_outcomes()

        message = app.stream.system.call_args.args[0]
        assert "Outcomes: 2" in message
        assert "claude=1" in message
        assert "agent_zero=1" in message
        assert "better_architecture=1" in message
        assert "bad_signal=1" in message
        print("PASS: /outcomes summarizes JSONL records")


def test_suggest_outcome_uses_agent_zero_without_recording_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {
                "claude": {},
                "codex": {},
                "agent_zero": {},
            }
        }
        app.ensure_project_files()
        app.chatboks_md.write_text(
            "\n".join(
                [
                    "[YOU] please review the timeout handling",
                    "[CODEX] Found a retry bug and added a focused test.\n>>> TASK_COMPLETE",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        app.load_agent_statuses = MagicMock(return_value={})
        app.update_state = MagicMock()
        app.check_token_limit = MagicMock()
        app.update_token_count = MagicMock()
        fake_agent = MagicMock()
        fake_agent.call.return_value = (
            '/win codex timeout_recovery high "Found and fixed the retry bug."\n'
            "Good fit because Codex both identified the defect and landed a test.\n"
            ">>> TASK_COMPLETE"
        )
        app.router.get_agent.return_value = fake_agent

        app.handle_user_input("/suggest-outcome codex")

        fake_agent.call.assert_called_once()
        prompt = fake_agent.call.call_args.args[0]
        assert "Target agent filter: codex" in prompt
        assert "[RECENT TRANSCRIPT]" in prompt
        message = app.stream.system.call_args.args[0]
        assert '/win codex timeout_recovery high "Found and fixed the retry bug."' in message
        assert app.load_outcomes() == []
        print("PASS: /suggest-outcome uses Agent Zero without recording JSONL")


if __name__ == "__main__":
    test_win_command_records_jsonl_without_agent_round()
    test_outcomes_summary_reads_jsonl()
    test_suggest_outcome_uses_agent_zero_without_recording_jsonl()
    print("\nAll outcome smoke tests passed.")
