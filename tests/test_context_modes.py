"""Smoke tests for Lean Context v1."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context.builder import ContextBuilder
from context.summarizer import Summarizer
from orchestrator import Chatboks


def _make_codegraph(root: Path) -> None:
    db = root / ".codegraph" / "codegraph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE files (path TEXT, language TEXT, node_count INTEGER)")
        conn.execute("CREATE TABLE nodes (kind TEXT, name TEXT, file_path TEXT, signature TEXT, start_line INTEGER)")
        conn.execute("CREATE TABLE edges (source TEXT, target TEXT, kind TEXT)")
        conn.execute("INSERT INTO files VALUES ('orchestrator.py', 'python', 10)")
        conn.execute("INSERT INTO nodes VALUES ('function', 'build_massive_context', 'orchestrator.py', 'def build_massive_context()', 12)")
        conn.execute("INSERT INTO edges VALUES ('Chatboks', 'ContextBuilder', 'calls')")


def _state(mode: str) -> dict:
    return {
        "round_intent": "respond",
        "context_mode": mode,
        "collaboration_mode": "default",
        "collaboration_mode_instruction": "Standard relay.",
        "expected_agents": ["claude", "codex"],
        "completed_agents": [],
        "next_agent": "claude",
        "context": {"token_counts": {}},
    }


def test_lean_context_omits_broad_codegraph_dumps():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _make_codegraph(root)
        chat = root / "chatboks.md"
        chat.write_text(
            "\n".join(
                [
                    "[YOU] turn one",
                    "[CLAUDE] turn two",
                    "[CODEX] turn three",
                    "[SYSTEM] turn four",
                ]
            ),
            encoding="utf-8",
        )
        builder = ContextBuilder(root, {})

        payload = builder.build(_state("lean"), chat)

        assert "[CODEGRAPH STATUS]" in payload
        assert "Key symbols" not in payload
        assert "Call/import relationships" not in payload
        assert "build_massive_context" not in payload
        assert "[CLAUDE] turn two" in payload
        assert "[YOU] turn one" not in payload


def test_full_context_includes_broad_codegraph_dumps():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _make_codegraph(root)
        chat = root / "chatboks.md"
        chat.write_text("[YOU] inspect code.\n", encoding="utf-8")
        builder = ContextBuilder(root, {})

        payload = builder.build(_state("full"), chat)

        assert "[CODEGRAPH] SQLite database" in payload
        assert "Key symbols" in payload
        assert "Call/import relationships" in payload
        assert "build_massive_context" in payload


def test_normal_context_preserves_checkpoint_summary_and_recent_tail():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _make_codegraph(root)
        chat = root / "chatboks.md"
        chat.write_text(
            "\n".join(
                [
                    "[YOU] old request",
                    "[CLAUDE] old analysis",
                    "[SYSTEM] >>> SUMMARY_CHECKPOINT",
                    "Agent: codex",
                    "Reason: token exhaustion",
                    "[SUMMARY]",
                    "- [YOU] old request",
                    "- >>> PROPOSAL",
                    ">>> SUMMARY_CHECKPOINT_END",
                    "[YOU] new request",
                    "[CODEX] fresh implementation notes",
                    "[SYSTEM] follow-up state",
                ]
            ),
            encoding="utf-8",
        )
        builder = ContextBuilder(root, {"context": {"recent_chatboks_lines": 2}})

        payload = builder.build(_state("normal"), chat)

        assert "[SYSTEM] >>> SUMMARY_CHECKPOINT" in payload
        assert "[SUMMARY]" in payload
        assert "- [YOU] old request" in payload
        assert "[YOU] new request" in payload
        assert "[SYSTEM] follow-up state" in payload
        assert "[CLAUDE] old analysis" not in payload


def test_lean_context_keeps_checkpoint_summary_with_recent_turns():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _make_codegraph(root)
        chat = root / "chatboks.md"
        chat.write_text(
            "\n".join(
                [
                    "[YOU] old request",
                    "[SYSTEM] >>> SUMMARY_CHECKPOINT",
                    "Agent: codex",
                    "Reason: token exhaustion",
                    "[SUMMARY]",
                    "- [YOU] old request",
                    "- [SYSTEM] preserved decision",
                    ">>> SUMMARY_CHECKPOINT_END",
                    "[YOU] current ask",
                    "[CLAUDE] current reply",
                ]
            ),
            encoding="utf-8",
        )
        builder = ContextBuilder(root, {})

        payload = builder.build(_state("lean"), chat)

        assert "[SYSTEM] >>> SUMMARY_CHECKPOINT" in payload
        assert "- [SYSTEM] preserved decision" in payload
        assert "[YOU] current ask" in payload
        assert "[CLAUDE] current reply" in payload


def test_summarizer_rolls_forward_checkpoint_without_repeating_markers():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        chat = root / "chatboks.md"
        chat.write_text(
            "\n".join(
                [
                    "[SYSTEM] >>> SUMMARY_CHECKPOINT",
                    "Agent: codex",
                    "Reason: token exhaustion",
                    "[SUMMARY]",
                    "- [YOU] prior task",
                    "- >>> PROPOSAL",
                    ">>> SUMMARY_CHECKPOINT_END",
                    "[SYSTEM] compacted once already",
                    "[YOU] continue from here",
                    "[CLAUDE] detailed analysis",
                    ">>> TASK_COMPLETE",
                ]
            ),
            encoding="utf-8",
        )

        summary = Summarizer(max_items=8).summarize(chat)

        assert "- [YOU] prior task" in summary
        assert "- >>> PROPOSAL" in summary
        assert "- [SYSTEM] compacted once already" in summary
        assert "- [YOU] continue from here" in summary
        assert "SUMMARY_CHECKPOINT_END" not in summary
        assert ">>> SUMMARY_CHECKPOINT" not in summary


def test_context_command_updates_state_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
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
        app.state = app.normalize_state({"session": "test", "round": 0, "status": "active"})
        app.save_state = MagicMock()
        app.run_agent_round = MagicMock()

        app.handle_user_input("/context full")

        assert app.state["context_mode"] == "full"
        app.run_agent_round.assert_not_called()


if __name__ == "__main__":
    test_lean_context_omits_broad_codegraph_dumps()
    test_full_context_includes_broad_codegraph_dumps()
    test_normal_context_preserves_checkpoint_summary_and_recent_tail()
    test_lean_context_keeps_checkpoint_summary_with_recent_turns()
    test_summarizer_rolls_forward_checkpoint_without_repeating_markers()
    test_context_command_updates_state_without_agent_round()
    print("\nAll context mode smoke tests passed.")
