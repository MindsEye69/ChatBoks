"""Smoke tests for local CLI latency summaries."""
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
    app.run_agent_round = MagicMock()
    return app


def test_latency_reports_no_records_yet():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/latency")

        message = app.stream.system.call_args.args[0]
        assert "No CLI latency records yet." in message
        app.run_agent_round.assert_not_called()
        print("PASS: /latency reports empty latency store")


def test_latency_summary_reads_recent_jsonl_records():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.ensure_project_files()
        app.cli_latency_path().write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-06-11T10:00:00",
                            "agent": "claude",
                            "mode": "respond",
                            "adapter_profile": "claude_cli_v1",
                            "total_seconds": 12.0,
                            "spawn_seconds": 0.5,
                            "first_output_seconds": 2.0,
                            "first_stdout_seconds": 2.4,
                            "runtime_seconds": 11.4,
                            "stdout_chars": 1200,
                            "stderr_chars": 0,
                        }
                    ),
                    "not json",
                    json.dumps(
                        {
                            "timestamp": "2026-06-11T10:01:00",
                            "agent": "codex",
                            "mode": "execute",
                            "adapter_profile": "codex_exec_v1",
                            "total_seconds": 8.0,
                            "spawn_seconds": 0.3,
                            "first_output_seconds": 0.6,
                            "first_stdout_seconds": 1.2,
                            "runtime_seconds": 7.7,
                            "stdout_chars": 800,
                            "stderr_chars": 120000,
                            "timeout_reason": "idle",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        app.handle_user_input("/latency 2")

        message = app.stream.system.call_args.args[0]
        assert "CLI latency: 2 recent calls" in message
        assert "claude/respond profile=claude_cli_v1" in message
        assert "codex/execute profile=codex_exec_v1" in message
        assert "first_output=0.600s" in message
        assert "first_stdout=1.200s" in message
        assert "err=120k" in message
        assert "timeout=idle" in message
        assert "Averages: total=10.000s spawn=0.400s first_output=1.300s first_stdout=1.800s runtime=9.550s" in message
        assert "Stderr-heavy runs: codex err=120k" in message
        app.run_agent_round.assert_not_called()
        print("PASS: /latency summarizes recent latency JSONL records")


def test_latency_summary_keeps_backward_compatible_field_aliases():
    lines = Chatboks.format_cli_latency_lines(
        [
            {
                "timestamp": "2026-06-11T10:02:00",
                "agent": "codex",
                "adapter_profile": "legacy",
                "duration_seconds": 3.0,
                "spawn_seconds": 0.1,
                "first_stdout_seconds": 1.0,
                "process_runtime_seconds": 2.9,
                "stdout_bytes": 123,
                "stderr_bytes": 0,
            }
        ]
    )

    message = "\n".join(lines)
    assert "total=3.000s" in message
    assert "first_output=1.000s" in message
    assert "runtime=2.900s" in message
    assert "out=123c err=0c" in message
    print("PASS: /latency keeps legacy field aliases")


if __name__ == "__main__":
    test_latency_reports_no_records_yet()
    test_latency_summary_reads_recent_jsonl_records()
    test_latency_summary_keeps_backward_compatible_field_aliases()
    print("\nAll latency smoke tests passed.")
