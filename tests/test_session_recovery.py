from __future__ import annotations

import json
import multiprocessing
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from context.builder import ContextBuilder
from orchestrator import Chatboks
from remote_control import RemoteEventBuffer, RemoteSession, parse_chatboks_messages


def make_app(root: Path, *, load_existing: bool = False) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "recovery-test"
    app.trigger = "manual"
    app.config = {"agents": {"codex": {}}, "context": {"resume_recent_turns": 8}}
    app.proj_config = {"agents": ["codex"], "primary": "codex"}
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.packet_file = root / ".chatboks" / "packets.jsonl"
    app.stream = MagicMock()
    app.stream.suppress_duplicate_stream_messages = True
    app.router = MagicMock()
    app.context = ContextBuilder(root, app.config)
    app._internal_write = False
    app._streamed_agent_responses = {}
    app._streaming_token_buffers = {}
    app._streaming_token_counts = {}
    app._last_streaming_token_save_at = {}
    app.input_buffer = []
    if load_existing:
        app.state = app.normalize_state(app.load_state())
    else:
        app.state = app.normalize_state(
            {
                "session": "recovery-test-session",
                "round": 4,
                "status": "active",
                "active_task": "Restore this exact task after restart.",
                "next_agent": "codex",
                "expected_agents": ["codex"],
                "completed_agents": [],
            }
        )
    return app


def run_live_session_until_killed(root_text: str, ready: multiprocessing.synchronize.Event) -> None:
    root = Path(root_text)
    app = make_app(root)
    app.ensure_project_files()
    app.append_message("you", "Process-kill prompt: preserve the exact visible conversation.")
    app.append_message("codex", "Process-kill response: recovery state is durable and ready.")
    app.update_state({"status": "active", "next_agent": "codex"})
    app.refresh_session_memory()
    ready.set()
    while True:
        time.sleep(0.1)


def test_session_journal_persists_transcript_snapshot_and_agent_memory(tmp_path: Path):
    app = make_app(tmp_path)
    app.ensure_project_files()
    app.append_message("you", "Keep the frosted navigation decision and finish recovery.")
    app.append_message("codex", "Implemented durable recovery and verified the journal path.")

    journal = app.current_session_journal()
    journal_text = journal.journal_path.read_text(encoding="utf-8")
    root_text = app.chatboks_md.read_text(encoding="utf-8")
    memory = journal.memory_path.read_text(encoding="utf-8")
    snapshot = json.loads(journal.snapshot_path.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in journal.events_path.read_text(encoding="utf-8").splitlines()]

    assert journal_text == root_text
    assert [event["sender"] for event in events[-2:]] == ["you", "codex"]
    assert snapshot["state"]["active_task"] == "Restore this exact task after restart."
    assert "[SESSION MEMORY - READ-ONLY RESTORE CONTEXT]" in memory
    assert "Restore this exact task after restart." in memory
    assert "Implemented durable recovery" in memory

    context = app.context.build(app.state, app.chatboks_md)
    assert "[SESSION MEMORY - READ-ONLY RESTORE CONTEXT]" in context
    assert "Keep the frosted navigation decision" in context
    assert "Implemented durable recovery" in context


def test_new_task_creates_separate_obsidian_journal(tmp_path: Path):
    app = make_app(tmp_path)
    app.ensure_project_files()
    app.append_message("you", "First task prompt")
    first = app.current_session_journal()
    first_text = first.journal_path.read_text(encoding="utf-8")

    new_session_id = app.start_new_session()
    app.append_message("system", "New task started. Previous task state cleared.")
    app.append_message("you", "Second task prompt")
    second = app.current_session_journal()

    assert new_session_id != "recovery-test-session"
    assert second.directory != first.directory
    assert first.journal_path.read_text(encoding="utf-8") == first_text
    assert "First task prompt" not in second.journal_path.read_text(encoding="utf-8")
    assert "Second task prompt" in second.journal_path.read_text(encoding="utf-8")
    assert "First task prompt" not in app.chatboks_md.read_text(encoding="utf-8")
    assert len(app.session_history()) == 2


def test_configured_obsidian_vault_receives_readable_journal_and_memory(tmp_path: Path):
    project = tmp_path / "project"
    vault = tmp_path / "vault"
    app = make_app(project)
    app.proj_config["obsidian_vault"] = str(vault)
    app.ensure_project_files()
    app.append_message("you", "Mirror this decision into the Obsidian vault.")
    app.append_message("codex", "Verified the Obsidian session mirror.")

    exported = vault / "ChatBoks" / "recovery-test" / "recovery-test-session"
    journal = (exported / "journal.md").read_text(encoding="utf-8")
    memory = (exported / "memory.md").read_text(encoding="utf-8")

    assert "tags: [chatboks, session]" in journal or "project: recovery-test" in journal
    assert "Mirror this decision" in journal
    assert "Verified the Obsidian session mirror" in journal
    assert "[SESSION MEMORY - READ-ONLY RESTORE CONTEXT]" in memory


def test_workbench_ui_state_is_validated_and_survives_restart(tmp_path: Path):
    app = make_app(tmp_path)
    app.ensure_project_files()
    remote = RemoteSession.__new__(RemoteSession)
    remote.lock = threading.RLock()
    remote.app = app

    result = remote.save_workbench_ui(
        {
            "session": app.state["session"],
            "theme": "console",
            "history_query": "accepted decision",
            "composer_draft": "Unsent draft",
            "composer_expanded": True,
            "focus_mode": False,
            "selected_skills": ["local:test"],
            "lanes": {"codex": {"at_bottom": False, "scroll_ratio": 0.35, "history_limit": 180}},
        }
    )

    restarted = make_app(tmp_path, load_existing=True)
    ui = restarted.state["workbench_ui"]
    assert result["saved"] is True
    assert ui["theme"] == "console"
    assert ui["history_query"] == "accepted decision"
    assert ui["composer_draft"] == "Unsent draft"
    assert ui["composer_expanded"] is True
    assert ui["lanes"]["codex"] == {"at_bottom": False, "scroll_ratio": 0.35, "history_limit": 180}


def test_newer_external_chatboks_mirror_is_reconciled_into_session(tmp_path: Path):
    app = make_app(tmp_path)
    app.ensure_project_files()
    app.append_message("you", "Original prompt")
    journal = app.current_session_journal()
    external_text = app.chatboks_md.read_text(encoding="utf-8") + "\n[SYSTEM] External watched update.\n"
    app.chatboks_md.write_text(external_text, encoding="utf-8")
    newer = journal.journal_path.stat().st_mtime_ns + 1_000_000_000
    os.utime(app.chatboks_md, ns=(newer, newer))

    app.handle_external_update()

    assert "External watched update." in journal.journal_path.read_text(encoding="utf-8")
    assert "External watched update." in app.context.build(app.state, app.chatboks_md)
    assert any(event.get("kind") == "compatibility_mirror_sync" for event in journal.recent_events())


def test_restart_marks_interrupted_session_resumable_with_context_ready(tmp_path: Path):
    original = make_app(tmp_path)
    original.ensure_project_files()
    original.append_message("you", "Continue from the durable design checkpoint.")
    original.append_message("codex", "Saved the accepted architecture and remaining verification step.")
    original.update_state({"status": "active", "next_agent": "codex"})

    restarted = make_app(tmp_path, load_existing=True)
    remote = RemoteSession.__new__(RemoteSession)
    remote.lock = threading.RLock()
    remote.app = restarted
    remote.events = RemoteEventBuffer()
    remote.configure_active_codegraph = MagicMock()
    restarted.initialize_agents = MagicMock()
    restarted.refresh_token_usage_display = MagicMock()

    remote.prepare()

    assert restarted.state["status"] == "awaiting_resume"
    assert restarted.state["active_task"] == "Restore this exact task after restart."
    transcript = parse_chatboks_messages(restarted.current_session_transcript(), limit=10_000)
    assert any(item["text"] == "Continue from the durable design checkpoint." for item in transcript)
    assert any("remaining verification step" in item["text"] for item in transcript)
    context = restarted.context.build(restarted.state, restarted.chatboks_md)
    assert "[SESSION MEMORY - READ-ONLY RESTORE CONTEXT]" in context
    assert "accepted architecture" in context
    assert "[ACTIVE TASK]\nRestore this exact task after restart." in context


def test_abrupt_process_kill_restores_exact_transcript_and_resume_context(tmp_path: Path):
    ready = multiprocessing.Event()
    process = multiprocessing.Process(target=run_live_session_until_killed, args=(str(tmp_path), ready))
    process.start()
    assert ready.wait(timeout=10)

    before = parse_chatboks_messages(tmp_path / "chatboks.md", limit=None)
    state_before = json.loads((tmp_path / ".chatboks" / "state.json").read_text(encoding="utf-8"))
    process.kill()
    process.join(timeout=10)
    assert not process.is_alive()

    restarted = make_app(tmp_path, load_existing=True)
    remote = RemoteSession.__new__(RemoteSession)
    remote.lock = threading.RLock()
    remote.app = restarted
    remote.events = RemoteEventBuffer()
    remote.configure_active_codegraph = MagicMock()
    restarted.initialize_agents = MagicMock()
    restarted.refresh_token_usage_display = MagicMock()
    remote.prepare()

    after = parse_chatboks_messages(restarted.current_session_transcript(), limit=None)
    context = restarted.context.build(restarted.state, restarted.chatboks_md)
    assert after == before
    assert restarted.state["session"] == state_before["session"]
    assert restarted.state["active_task"] == state_before["active_task"]
    assert restarted.state["status"] == "awaiting_resume"
    assert "Process-kill prompt" in context
    assert "Process-kill response" in context
