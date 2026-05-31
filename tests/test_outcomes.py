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


if __name__ == "__main__":
    test_win_command_records_jsonl_without_agent_round()
    test_outcomes_summary_reads_jsonl()
    print("\nAll outcome smoke tests passed.")
