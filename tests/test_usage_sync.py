"""Smoke tests for usage baseline syncing and summaries."""
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
    return app


def test_usage_show_reports_no_records_yet():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/usage")

        message = app.stream.system.call_args.args[0]
        assert "No usage baselines saved yet." in message
        assert "anthropic" in message
        print("PASS: /usage reports empty baseline store")


def test_usage_sync_records_playwright_capture_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {}
        app.capture_usage_baseline = MagicMock(
            return_value={
                "timestamp": "2026-06-08T12:00:00",
                "project": "test",
                "provider": "openai",
                "label": "OpenAI Platform",
                "final_url": "https://platform.openai.com/usage",
                "title": "Usage",
                "status": "ok",
                "login_required": False,
                "highlights": ["Total spend $12.34", "Tokens 456k"],
            }
        )

        app.handle_user_input("/usage sync openai")

        records = app.load_usage_baselines()
        assert len(records) == 1
        assert records[0]["provider"] == "openai"
        assert records[0]["highlights"] == ["Total spend $12.34", "Tokens 456k"]
        message = app.stream.system.call_args.args[0]
        assert "Usage baseline saved for openai" in message
        print("PASS: /usage sync records baseline metadata")


def test_usage_summary_reads_saved_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.ensure_project_files()
        app.usage_baselines_path().write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-06-08T12:00:00",
                            "provider": "anthropic",
                            "title": "Anthropic Usage",
                            "highlights": ["Spend $4.20"],
                            "login_required": False,
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-06-08T12:05:00",
                            "provider": "openai",
                            "title": "OpenAI Usage",
                            "highlights": ["Tokens 300k"],
                            "login_required": True,
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        app.show_usage_baselines()

        message = app.stream.system.call_args.args[0]
        assert "Usage baselines: 2" in message
        assert "anthropic: ready" in message
        assert "openai: login required" in message
        print("PASS: /usage summarizes saved baseline records")


def test_extract_usage_highlights_filters_relevant_lines():
    lines = "\n".join(
        [
            "Welcome back",
            "Usage this month",
            "Total spend $7.10",
            "API token limit 500k",
            "Other navigation",
        ]
    )

    highlights = Chatboks.extract_usage_highlights(lines)

    assert highlights == [
        "Usage this month",
        "Total spend $7.10",
        "API token limit 500k",
    ]
    print("PASS: usage highlight extraction keeps relevant lines")


if __name__ == "__main__":
    test_usage_show_reports_no_records_yet()
    test_usage_sync_records_playwright_capture_metadata()
    test_usage_summary_reads_saved_jsonl()
    test_extract_usage_highlights_filters_relevant_lines()
    print("\nAll usage sync smoke tests passed.")
