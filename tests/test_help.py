"""Smoke tests for the local /help command."""
from __future__ import annotations

import io
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import Chatboks, HELP_COMMANDS
from ui.stream import Stream


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


def test_help_command_renders_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/help")

        app.stream.help_box.assert_called_once_with(HELP_COMMANDS)
        app.run_agent_round.assert_not_called()
        print("PASS: /help renders locally without routing to agents")


def test_help_pin_commands_toggle_prompt_strip():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.handle_user_input("/help unpin")

        assert app.state["help_pin"] is False
        app.save_state.assert_called()
        app.stream.system.assert_called_with("Pinned prompt help is off. Use /help pin to show it again.")

        app.handle_user_input("/help pin")

        assert app.state["help_pin"] is True
        app.stream.system.assert_called_with("Pinned prompt help is on. Use /help unpin to hide it.")
        print("PASS: /help pin and /help unpin toggle prompt strip")


def test_prompt_help_pin_respects_state():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        app.show_prompt_help_pin()
        app.stream.help_pin.assert_called_once()

        app.stream.help_pin.reset_mock()
        app.state["help_pin"] = False
        app.show_prompt_help_pin()
        app.stream.help_pin.assert_not_called()

        app.show_prompt_help_pin(force=True)
        app.stream.help_pin.assert_called_once()
        print("PASS: prompt help pin respects state and force preview")


def test_graph_command_renders_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()
        app.codegraph_status_lines = MagicMock(return_value=["- CodeGraph: OK"])
        app.graphify_status_lines = MagicMock(return_value=["- Graphify: OK"])

        app.handle_user_input("/graph")

        app.stream.system.assert_called_once_with("Graph status:\n- CodeGraph: OK\n- Graphify: OK")
        app.run_agent_round.assert_not_called()
        print("PASS: /graph renders locally without routing to agents")


def test_codegraph_status_lines_reads_sqlite_counts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "codegraph.db"
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE files (id INTEGER)")
            conn.execute("CREATE TABLE nodes (id INTEGER)")
            conn.execute("CREATE TABLE edges (id INTEGER)")
            conn.executemany("INSERT INTO files VALUES (?)", [(1,), (2,)])
            conn.executemany("INSERT INTO nodes VALUES (?)", [(1,), (2,), (3,)])
            conn.executemany("INSERT INTO edges VALUES (?)", [(1,)])
            conn.commit()
        finally:
            conn.close()

        app = _make_app(root)
        app.context.find_codegraph_db.return_value = db

        lines = app.codegraph_status_lines()

        assert lines[0] == "- CodeGraph: OK (2 files, 3 nodes, 1 edges)"
        assert str(db) in lines[1]
        print("PASS: /graph CodeGraph status reads sqlite counts")


def test_graphify_status_lines_reports_fresh_graph():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir()
        (graph_dir / "graph.json").write_text("{}", encoding="utf-8")
        (graph_dir / "GRAPH_TREE.html").write_text("<html></html>", encoding="utf-8")
        (graph_dir / "GRAPH_REPORT.md").write_text(
            "- 877 nodes · 2170 edges · 44 communities\n"
            "- Built from commit: `abc12345`\n",
            encoding="utf-8",
        )
        app = _make_app(root)
        app.latest_source_commit = MagicMock(return_value="abc12345deadbeef")
        app.source_worktree_dirty = MagicMock(return_value=False)

        lines = app.graphify_status_lines()

        assert any("Summary: 877 nodes" in line for line in lines)
        assert any("Freshness: OK" in line for line in lines)
        print("PASS: /graph Graphify status reports fresh graph")


def test_graphify_status_lines_reports_stale_graph():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        graph_dir = root / "graphify-out"
        graph_dir.mkdir()
        (graph_dir / "graph.json").write_text("{}", encoding="utf-8")
        (graph_dir / "GRAPH_REPORT.md").write_text(
            "- Built from commit: `abc12345`\n",
            encoding="utf-8",
        )
        app = _make_app(root)
        app.latest_source_commit = MagicMock(return_value="def67890")
        app.source_worktree_dirty = MagicMock(return_value=False)

        lines = app.graphify_status_lines()

        assert any("Freshness: STALE" in line for line in lines)
        assert any("graphify update ." in line for line in lines)
        print("PASS: /graph Graphify status reports stale graph")


def test_stream_help_box_contains_bbs_frame_and_commands():
    buffer = io.StringIO()
    stream = Stream({}, [])
    stream.console = Console(file=buffer, width=80, color_system=None)

    stream.help_box(HELP_COMMANDS)

    output = buffer.getvalue()
    assert "+-" in output
    assert "CHATBOKS COMMAND DECK" in output
    assert "/agent" in output
    assert "APPROVE / MODIFY / REJECT" in output
    print("PASS: help box renders command deck")


def test_stream_help_pin_contains_compact_commands():
    buffer = io.StringIO()
    stream = Stream({}, [])
    stream.console = Console(file=buffer, width=80, color_system=None)

    stream.help_pin(["/help", "/agent", "@zero", "exit"])

    output = buffer.getvalue()
    assert "commands:" in output
    assert "/help" in output
    assert "@zero" in output
    assert "exit" in output
    print("PASS: compact help pin renders prompt command strip")


def test_stream_token_usage_renders_session_bars():
    stream = Stream(
        {
            "claude": {"token_limit": 180_000, "token_warning": 150_000},
            "codex": {"token_limit": 120_000, "token_warning": 100_000},
            "agent_zero": {"token_limit": 32_000, "token_warning": 24_000},
        },
        ["claude", "codex"],
    )

    line = stream.build_token_usage_line(
        {"claude": 90_000, "codex": 12_000, "agent_zero": 4_000},
        {"used": 106_000, "warning": 220_000, "limit": 280_000},
    )

    assert "session tokens:" in line
    assert "CLAUDE" in line
    assert "CODEX" in line
    assert "AGENT_ZERO" in line
    assert "TOTAL" in line
    assert "[green][#####-----][/green]" in line
    print("PASS: token usage bar renders configured and extra-count agents")


def test_stream_standby_uses_agent_label():
    buffer = io.StringIO()
    stream = Stream({"agent_zero": {"color": "magenta"}}, [])
    stream.console = Console(file=buffer, width=80, color_system=None)

    stream.standby("agent_zero", "Standby via @zero. Available on demand.")

    output = buffer.getvalue()
    assert "[AGENT_ZERO]" in output
    assert "Standby via @zero. Available on demand." in output
    print("PASS: standby line renders with agent label")


if __name__ == "__main__":
    test_help_command_renders_without_agent_round()
    test_help_pin_commands_toggle_prompt_strip()
    test_prompt_help_pin_respects_state()
    test_graph_command_renders_without_agent_round()
    test_codegraph_status_lines_reads_sqlite_counts()
    test_graphify_status_lines_reports_fresh_graph()
    test_graphify_status_lines_reports_stale_graph()
    test_stream_help_box_contains_bbs_frame_and_commands()
    test_stream_help_pin_contains_compact_commands()
    test_stream_token_usage_renders_session_bars()
    test_stream_standby_uses_agent_label()
    print("\nAll help smoke tests passed.")
