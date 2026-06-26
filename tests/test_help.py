"""Smoke tests for the local /help command."""
from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_resume_command_renders_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()
        app.resume_project_lines = MagicMock(return_value=["- Project: test"])
        app.resume_git_lines = MagicMock(return_value=["- Git: main, clean"])
        app.codegraph_status_lines = MagicMock(return_value=["- CodeGraph: OK"])
        app.graphify_status_lines = MagicMock(return_value=["- Graphify: OK"])
        app.sleep_memory_status_lines = MagicMock(return_value=(["- Sleep memory: 3 items"], True))
        app.packet_status_lines = MagicMock(return_value=["- Thought packets: 2 captured"])
        app.resume_session_lines = MagicMock(return_value=["- Session: idle"])
        app.resume_next_action_lines = MagicMock(return_value=["- Next action: Ready for work."])

        app.handle_user_input("/resume")

        app.stream.system.assert_called_once_with(
            "Resume readiness:\n"
            "- Project: test\n"
            "- Git: main, clean\n"
            "- CodeGraph: OK\n"
            "- Graphify: OK\n"
            "- Sleep memory: 3 items\n"
            "- Thought packets: 2 captured\n"
            "- Session: idle\n"
            "- Next action: Ready for work."
        )
        app.run_agent_round.assert_not_called()
        print("PASS: /resume renders locally without routing to agents")

def test_session_command_reports_dashboard_usage_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/session")

        app.stream.system.assert_called_once_with(
            "Session workflow: use /session start or /session close. "
            "These run DasDashboard's project-dashboard checks for this project."
        )
        app.run_agent_round.assert_not_called()
        print("PASS: /session reports DasDashboard workflow usage without routing to agents")


def test_tickets_command_lists_open_paper_sleuth_tickets_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paper_root = root / "Paper Sleuth"
        ticket_dir = paper_root / "research" / "tickets" / "test"
        ticket_dir.mkdir(parents=True)
        (ticket_dir / "p1-ticket.md").write_text(
            "# Useful MCP Gate\n\n"
            "Status: open\n"
            "Priority: P1\n\n"
            "## Finding Summary\n\n"
            "A useful hardening idea.\n\n"
            "## Source URLs\n\n"
            "- https://example.test/paper\n",
            encoding="utf-8",
        )
        (ticket_dir / "deferred-ticket.md").write_text(
            "# Parked Idea\n\n"
            "Status: deferred\n"
            "Priority: P2\n\n",
            encoding="utf-8",
        )
        app = _make_app(root)
        app.run_agent_round = MagicMock()

        with patch.dict("orchestrator.os.environ", {"PAPER_SLEUTH_ROOT": str(paper_root)}):
            app.handle_user_input("/tickets")

        output = app.stream.system.call_args.args[0]
        assert "Paper Sleuth tickets for test: 2 total, 1 open." in output
        assert "- P1 Useful MCP Gate" in output
        assert "Source: https://example.test/paper" in output
        assert "Next: Triage now" in output
        assert "Parked Idea" not in output
        app.run_agent_round.assert_not_called()
        print("PASS: /tickets lists open Paper Sleuth tickets without routing to agents")


def test_tickets_all_includes_non_open_status_groups():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paper_root = root / "Paper Sleuth"
        ticket_dir = paper_root / "research" / "tickets" / "test"
        ticket_dir.mkdir(parents=True)
        (ticket_dir / "open-ticket.md").write_text(
            "# Open Idea\n\nStatus: open\nPriority: P1\n",
            encoding="utf-8",
        )
        (ticket_dir / "deferred-ticket.md").write_text(
            "# Deferred Idea\n\nStatus: deferred\nPriority: P2\n",
            encoding="utf-8",
        )
        app = _make_app(root)

        with patch.dict("orchestrator.os.environ", {"PAPER_SLEUTH_ROOT": str(paper_root)}):
            app.handle_user_input("/tickets all")

        output = app.stream.system.call_args.args[0]
        assert "Open:" in output
        assert "Deferred:" in output
        assert "Open Idea [open]" in output
        assert "Deferred Idea [deferred]" in output
        print("PASS: /tickets all includes non-open ticket groups")


def test_session_start_invokes_dashboard_procedure_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dashboard_root = root / "DasDashboard"
        app = _make_app(root)
        app.run_agent_round = MagicMock()
        app.dasdashboard_root = MagicMock(return_value=dashboard_root)
        payload = {
            "ok": True,
            "command": "session-start",
            "written": {
                "dashboardMarkdown": str(root / "dashboard.md"),
                "latestFile": str(root / "dashboards" / "latest.json"),
                "sessionFile": str(root / "dashboards" / "sessions" / "stamp.json"),
            },
            "snapshot": {
                "git": {"status": "main, clean", "clean": True},
                "paperSleuth": {"status": "3 tickets found", "openTicketCount": 7},
                "codeGraph": {"status": "OK"},
                "graphify": {"status": "configured"},
            },
        }
        with (
            patch("orchestrator.shutil.which", return_value="npm.cmd"),
            patch(
                "orchestrator.subprocess.run",
                return_value=subprocess.CompletedProcess(["npm"], 0, json.dumps(payload), ""),
            ) as run,
        ):
            app.handle_user_input("/session start")

        args, kwargs = run.call_args
        assert args[0] == ["npm.cmd", "run", "session:start", "--", str(root)]
        assert kwargs["cwd"] == dashboard_root
        summary = app.stream.system.call_args_list[-1].args[0]
        assert "DasDashboard /session start complete." in summary
        assert "Command: npm run session:start --" in summary
        assert "Paper Sleuth: 3 tickets found (7 open total)" in summary
        assert "Wrote dashboard.md:" in summary
        app.run_agent_round.assert_not_called()
        print("PASS: /session start invokes DasDashboard without routing to agents")


def test_session_close_reports_dirty_git_gate_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dashboard_root = root / "DasDashboard"
        app = _make_app(root)
        app.run_agent_round = MagicMock()
        app.dasdashboard_root = MagicMock(return_value=dashboard_root)
        payload = {
            "ok": True,
            "command": "session-close",
            "written": {
                "dashboardMarkdown": str(root / "dashboard.md"),
                "latestFile": str(root / "dashboards" / "latest.json"),
                "sessionFile": str(root / "dashboards" / "sessions" / "stamp.json"),
            },
            "snapshot": {
                "git": {"status": "main, dirty (2 pending changes)", "clean": False},
                "paperSleuth": {"status": "3 tickets found", "openTicketCount": 7},
                "codeGraph": {"status": "OK"},
                "graphify": {"status": "configured"},
            },
        }
        with (
            patch("orchestrator.shutil.which", return_value="npm.cmd"),
            patch(
                "orchestrator.subprocess.run",
                return_value=subprocess.CompletedProcess(["npm"], 2, json.dumps(payload), ""),
            ) as run,
        ):
            app.handle_user_input("/session close")

        args, _kwargs = run.call_args
        assert args[0] == ["npm.cmd", "run", "session:close", "--", str(root)]
        summary = app.stream.system.call_args_list[-1].args[0]
        assert "close readiness failed because git is dirty" in summary
        assert "Next action: commit, stash, or intentionally discard pending changes" in summary
        assert "Command: npm run session:close --" in summary
        assert "Git: main, dirty (2 pending changes)" in summary
        app.run_agent_round.assert_not_called()
        print("PASS: /session close reports DasDashboard dirty-git close gate")


def test_resume_git_lines_reports_dirty_count():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_git = MagicMock(
            side_effect=[
                subprocess.CompletedProcess(["git"], 0, "main\n", ""),
                subprocess.CompletedProcess(["git"], 0, " M orchestrator.py\n?? tests/test_resume.py\n", ""),
            ]
        )

        lines = app.resume_git_lines()

        assert lines == ["- Git: main, dirty (2 pending changes)"]
        print("PASS: /resume git status reports dirty count")


def test_sleep_memory_status_lines_reads_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sleep_dir = root / ".chatboks" / "sleep"
        sleep_dir.mkdir(parents=True)
        (sleep_dir / "latest.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-06-10T12:00:00+02:00",
                    "items": 4,
                    "summary_path": str(sleep_dir / "latest.md"),
                }
            ),
            encoding="utf-8",
        )
        app = _make_app(root)

        lines, has_sleep = app.sleep_memory_status_lines()

        assert has_sleep is True
        assert lines[0] == "- Sleep memory: 4 items, last consolidated 2026-06-10T12:00:00+02:00"
        assert str(sleep_dir / "latest.md") in lines[1]
        print("PASS: /resume reads sleep memory metadata")


def test_packet_status_lines_reports_latest_packet():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        packet_file = root / ".chatboks" / "packets.jsonl"
        packet_file.parent.mkdir(parents=True)
        packet_file.write_text(
            json.dumps(
                {
                    "sender": "codex",
                    "packet": {
                        "agent": "codex",
                        "stance": "VERIFY",
                        "observed": ["tests passed"],
                        "risks": [],
                        "next_action": "commit when ready",
                        "signal": "TASK_COMPLETE",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        app = _make_app(root)
        app.packet_file = packet_file

        lines = app.packet_status_lines()

        assert lines[0] == "- Thought packets: 1 captured"
        assert lines[1] == "  Latest: codex VERIFY -> TASK_COMPLETE; observed 1, risks 0"
        assert lines[2] == "  Next action: commit when ready"
        print("PASS: /resume reports latest thought packet")


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

    stream.help_pin(["/help", "/agent", "@coordinator", "exit"])

    output = buffer.getvalue()
    assert "commands:" in output
    assert "/help" in output
    assert "@coordinator" in output
    assert "exit" in output
    print("PASS: compact help pin renders prompt command strip")


def test_stream_token_usage_renders_session_bars():
    stream = Stream(
        {
            "claude": {"token_limit": 180_000, "token_warning": 150_000},
            "codex": {"token_limit": 120_000, "token_warning": 100_000},
            "coordinator": {"token_limit": 32_000, "token_warning": 24_000},
        },
        ["claude", "codex"],
    )

    line = stream.build_token_usage_line(
        {"claude": 90_000, "codex": 12_000, "coordinator": 4_000},
        {"used": 106_000, "warning": 220_000, "limit": 280_000},
    )

    assert "session tokens:" in line
    assert "CLAUDE" in line
    assert "CODEX" in line
    assert "COORDINATOR" in line
    assert "TOTAL" in line
    assert "[green][#####-----][/green]" in line
    print("PASS: token usage bar renders configured and extra-count agents")


def test_stream_standby_uses_agent_label():
    buffer = io.StringIO()
    stream = Stream({"coordinator": {"color": "magenta"}}, [])
    stream.console = Console(file=buffer, width=80, color_system=None)

    stream.standby("coordinator", "Standby via @coordinator. Available on demand.")

    output = buffer.getvalue()
    assert "[COORDINATOR]" in output
    assert "Standby via @coordinator. Available on demand." in output
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
