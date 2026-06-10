"""Smoke tests for Lean Context v1."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_context_includes_sleep_memory_artifact():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        _make_codegraph(root)
        sleep_dir = root / ".chatboks" / "sleep"
        sleep_dir.mkdir(parents=True)
        (sleep_dir / "latest.md").write_text(
            "[SLEEP MEMORY - READ-ONLY CONSOLIDATED CONTEXT]\n"
            "[SUMMARY]\n"
            "- [YOU] preserved sleep decision\n",
            encoding="utf-8",
        )
        chat = root / "chatboks.md"
        chat.write_text("[YOU] fresh ask\n", encoding="utf-8")
        builder = ContextBuilder(root, {})

        payload = builder.build(_state("lean"), chat)

        assert "[SLEEP MEMORY - READ-ONLY CONSOLIDATED CONTEXT]" in payload
        assert "- [YOU] preserved sleep decision" in payload
        assert "[YOU] fresh ask" in payload


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
        assert "Recent user requests:" in summary
        assert "- continue from here" in summary
        assert "compacted once already" not in summary
        assert "TASK_COMPLETE" not in summary
        assert "SUMMARY_CHECKPOINT_END" not in summary
        assert ">>> SUMMARY_CHECKPOINT" not in summary


def test_summarizer_filters_role_call_and_groups_durable_items():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        chat = root / "chatboks.md"
        chat.write_text(
            "\n".join(
                [
                    "[YOU] role call",
                    "[CLAUDE] Claude online. Role: architecture and review.",
                    ">>> TASK_COMPLETE",
                    "[YOU] Tighten mobile remote authentication failure handling.",
                    "[CLAUDE] CHALLENGE: Missing retry feedback is a UX risk on mobile.",
                    ">>> HANDOFF",
                    "[CODEX] Implemented clearer failed-to-fetch handling and verified tests passed.",
                    ">>> TASK_COMPLETE",
                    "[SYSTEM] Commit by MindsEye69: Stabilize mobile remote bridge UI (caf350c)",
                ]
            ),
            encoding="utf-8",
        )

        summary = Summarizer(max_items=12).summarize(chat)

        assert "Recent user requests:" in summary
        assert "- Tighten mobile remote authentication failure handling." in summary
        assert "Open risks:" in summary
        assert "UX risk on mobile" in summary
        assert "Verified facts:" in summary
        assert "Implemented clearer failed-to-fetch handling" in summary
        assert "Tests and commits:" in summary
        assert "Stabilize mobile remote bridge UI" in summary
        assert "role call" not in summary.lower()
        assert "TASK_COMPLETE" not in summary


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


def test_sleep_command_writes_memory_and_stays_local():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = Chatboks.__new__(Chatboks)
        app.project = "test"
        app.trigger = "manual"
        app.config = {"agents": {"codex": {}}}
        app.proj_config = {"agents": ["codex"]}
        app.proj_path = root
        app.chatboks_md = root / "chatboks.md"
        app.chatboks_md.write_text("[YOU] keep this decision\n", encoding="utf-8")
        app.state_file = root / ".chatboks" / "state.json"
        app.stream = MagicMock()
        app.router = MagicMock()
        app.context = MagicMock()
        app.context.summarize.return_value = "[SUMMARY]\n- [YOU] keep this decision"
        app.sleep_closure_lines = MagicMock(return_value=["Sleep complete. Work block closed."])
        app._internal_write = False
        app.input_buffer = []
        app.state = app.normalize_state({"session": "test", "round": 0, "status": "active"})
        app.save_state = MagicMock()
        app.run_agent_round = MagicMock()

        app.handle_user_input("/sleep")

        latest = root / ".chatboks" / "sleep" / "latest.md"
        metadata = root / ".chatboks" / "sleep" / "latest.json"
        history = root / ".chatboks" / "sleep" / "history.jsonl"
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        assert latest.exists()
        assert metadata.exists()
        assert history.exists()
        assert "[SLEEP MEMORY - READ-ONLY CONSOLIDATED CONTEXT]" in latest.read_text(encoding="utf-8")
        assert "- [YOU] keep this decision" in latest.read_text(encoding="utf-8")
        assert ">>> SUMMARY_CHECKPOINT" in transcript
        assert "Reason: manual sleep consolidation" in transcript
        assert app.state["last_sleep"]["items"] == 1
        app.stream.system.assert_called_once_with("Sleep complete. Work block closed.")
        app.run_agent_round.assert_not_called()


def test_sleep_closure_runs_codegraph_sync_and_reports_status():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        app = Chatboks.__new__(Chatboks)
        app.config = {}
        app.proj_path = root
        app.context = MagicMock()
        app.context.find_codegraph_db.return_value = root / ".codegraph" / "codegraph.db"
        _make_codegraph(root)

        with patch("orchestrator.shutil.which", return_value="codegraph"), patch(
            "orchestrator.subprocess.run",
            return_value=subprocess.CompletedProcess(["codegraph", "sync"], 0, "synced", ""),
        ) as run:
            lines = app.codegraph_sync_closure_lines()

        run.assert_called_once()
        assert lines[0] == "- CodeGraph sync: OK"
        assert any("CodeGraph: OK" in line for line in lines)


def test_sleep_closure_reports_graphify_warning_and_git_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = Chatboks.__new__(Chatboks)
        app.project = "test"
        app.proj_path = root
        app.run_git = MagicMock(
            side_effect=[
                subprocess.CompletedProcess(["git"], 0, "main\n", ""),
                subprocess.CompletedProcess(["git"], 0, "", ""),
            ]
        )

        graphify_lines = app.graphify_sleep_closure_lines()
        git_lines = app.git_sleep_closure_lines()

        assert any("Graphify: WARN" in line for line in graphify_lines)
        assert graphify_lines[-1] == "  Sleep note: refresh Graphify after source/doc changes are committed."
        assert git_lines == ["- Git: main, clean"]


if __name__ == "__main__":
    test_lean_context_omits_broad_codegraph_dumps()
    test_full_context_includes_broad_codegraph_dumps()
    test_normal_context_preserves_checkpoint_summary_and_recent_tail()
    test_lean_context_keeps_checkpoint_summary_with_recent_turns()
    test_context_includes_sleep_memory_artifact()
    test_summarizer_rolls_forward_checkpoint_without_repeating_markers()
    test_summarizer_filters_role_call_and_groups_durable_items()
    test_context_command_updates_state_without_agent_round()
    test_sleep_command_writes_memory_and_stays_local()
    test_sleep_closure_runs_codegraph_sync_and_reports_status()
    test_sleep_closure_reports_graphify_warning_and_git_state()
    print("\nAll context mode smoke tests passed.")
