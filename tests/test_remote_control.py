from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_control import (
    MAX_JSON_BODY_BYTES,
    MAX_TRANSCRIPT_LIMIT,
    MODEL_CHOICES,
    PAIR_FAILURE_LIMIT,
    PairingRateLimited,
    RemoteEventBuffer,
    RemoteAuth,
    RemoteBridgeServer,
    RemoteHandler,
    RemoteSession,
    agent_trace_from_transcript,
    build_lane_agents,
    build_token_usage,
    codegraph_stats,
    ensure_operator_file_available,
    git_environment,
    is_allowed_bind_host,
    is_allowed_app_origin,
    is_collaboration_mode_command,
    is_tailnet_ipv4_host,
    parse_chatboks_messages,
    packet_trace_from_file,
    proposal_snapshot,
    normalize_agent_model,
    rotate_pair_code_from_operator_file,
    trace_snapshot,
)


class FakeSession:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.snapshot_calls: list[tuple[int, int]] = []
        self.completion_queries: list[str] = []
        self.project = "chatboks"
        self.projects = ["biosassist", "chatboks"]

    def workbench_status(self) -> dict[str, object]:
        return {
            "project": self.project,
            "generated_at": "12:00:00",
            "environment": {"branch": "main", "staged": 0, "unstaged": 2, "clean": False},
            "graph": {"healthy": True, "files": 52, "nodes": 1363, "edges": 1545},
            "monitor": {"pid": 1234},
        }

    def command_completions(self, value: str) -> dict[str, object]:
        self.completion_queries.append(value)
        return {"options": [{"replacement": "/mode brainstorm", "label": "Brainstorm mode"}]}

    def snapshot(self, cursor: int = 0, transcript_limit: int | None = 120) -> dict[str, object]:
        self.snapshot_calls.append((cursor, transcript_limit))
        return {
            "project": self.project,
            "projects": self.projects,
            "status": "active",
            "active_task": "test",
            "next_agent": "codex",
            "criteria_gate": None,
            "token_line": "session tokens: CODEX 1.0k/120k",
            "transcript": [{"id": 0, "sender": "you", "text": "hello"}],
            "events": [{"id": cursor + 1, "sender": "system", "text": "ok"}],
        }

    def submit(self, text: str, skills: object | None = None) -> dict[str, object]:
        _ = skills
        self.commands.append(text)
        return self.snapshot()

    def start_new_task(self) -> dict[str, object]:
        self.commands.append("/new-task")
        return {
            **self.snapshot(),
            "status": "idle",
            "active_task": None,
            "events": [{"id": 1, "sender": "system", "text": "New task ready."}],
        }

    def available_projects(self) -> list[str]:
        return self.projects

    def project_catalog(self) -> list[dict[str, object]]:
        return [{"name": project, "path": "", "agents": [], "direct_agents": [], "primary": ""} for project in self.projects]

    def switch_project(self, project: str) -> dict[str, object]:
        if project not in self.projects:
            raise ValueError(f"Unknown project '{project}'.")
        self.project = project
        return self.snapshot()


class BlockingFakeApp:
    def __init__(self, transcript: Path, started: threading.Event, release: threading.Event) -> None:
        self.project = "chatboks"
        self.config = {"projects": {"chatboks": {}}}
        self.state = {"status": "active", "context": {"token_counts": {"codex": 42}}}
        self.chatboks_md = transcript
        self.packet_file = transcript.parent / "packets.jsonl"
        self.stream = FakeStream()
        self.started = started
        self.release = release

    def handle_user_input(self, text: str) -> None:
        self.state["active_task"] = text
        self.started.set()
        assert self.release.wait(timeout=5)
        self.chatboks_md.write_text("[YOU] hello\n[CODEX] done\n", encoding="utf-8")

    def load_state(self) -> dict[str, object]:
        return self.state

    def session_token_budget(self) -> int:
        return 120_000


class FakeStream:
    def build_token_usage_line(self, token_counts: dict[str, int], session_budget: int) -> str:
        return f"session tokens: CODEX {token_counts.get('codex', 0)}/{session_budget}"


def run_server(
    session: FakeSession,
    token: str,
    operator_file: Path | None = None,
) -> tuple[RemoteBridgeServer, threading.Thread, str]:
    server = RemoteBridgeServer(("127.0.0.1", 0), RemoteHandler, session, RemoteAuth(token), operator_file)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


def test_parse_chatboks_messages_reads_multiline_turns(tmp_path: Path):
    transcript = tmp_path / "chatboks.md"
    transcript.write_text(
        "---\nproject: chatboks\n---\n[SYSTEM] Booted.\n[YOU] hello\ncontinued\n[CODEX] hi there\n",
        encoding="utf-8",
    )

    messages = parse_chatboks_messages(transcript)

    assert messages == [
        {"id": 0, "sender": "system", "text": "Booted."},
        {"id": 1, "sender": "you", "text": "hello\ncontinued"},
        {"id": 2, "sender": "codex", "text": "hi there"},
    ]

    assert parse_chatboks_messages(transcript, limit=None) == messages
    print("PASS: remote transcript parsing keeps multiline turns intact")


def test_agent_trace_extracts_signals_and_handoff_targets():
    messages = [
        {
            "id": 3,
            "sender": "claude",
            "text": "Architecture pass complete.\n>>> HANDOFF >> Codex",
        },
        {
            "id": 4,
            "sender": "codex",
            "text": "Implementation verified.\n>>> TASK_COMPLETE",
        },
    ]

    trace = agent_trace_from_transcript(messages)

    assert trace == [
        {
            "message_id": 3,
            "agent": "claude",
            "signal": "HANDOFF",
            "target": "Codex",
            "summary": "Architecture pass complete.",
        },
        {
            "message_id": 4,
            "agent": "codex",
            "signal": "TASK_COMPLETE",
            "target": None,
            "summary": "Implementation verified.",
        },
    ]
    print("PASS: agent trace extracts transcript signals and handoff targets")


def test_packet_trace_reads_compact_packet_records(tmp_path: Path):
    packet_file = tmp_path / "packets.jsonl"
    packet_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-12T09:00:00",
                "round": 7,
                "context": {"confirmation": {"stage": "executor"}},
                "packet": {
                    "agent": "codex",
                    "stance": "VERIFY",
                    "observed": ["tests pass", "ui checked"],
                    "risks": ["needs browser pass"],
                    "next_action": "Run UI check",
                    "signal": "TASK_COMPLETE",
                },
            }
        )
        + "\nnot-json\n",
        encoding="utf-8",
    )

    trace = packet_trace_from_file(packet_file)

    assert trace == [
        {
            "timestamp": "2026-06-12T09:00:00",
            "agent": "codex",
            "stance": "VERIFY",
            "signal": "TASK_COMPLETE",
            "next_action": "Run UI check",
            "observed_count": 2,
            "risk_count": 1,
            "round": 7,
            "stage": "executor",
        }
    ]
    print("PASS: packet trace reads compact packet records")


def test_remote_event_buffer_preserves_stream_delta_whitespace():
    buffer = RemoteEventBuffer()

    buffer.append("message_delta", "claude", "Short")
    buffer.append("message_delta", "claude", " ")
    buffer.append("message_delta", "claude", "answer")
    buffer.append("system", "system", "  done  ")

    events = buffer.since(0)

    assert [event["text"] for event in events[:3]] == ["Short", " ", "answer"]
    assert events[3]["text"] == "done"
    print("PASS: streamed deltas preserve whitespace while normal events stay trimmed")


def test_lane_agents_replace_exhausted_main_agent_with_active_fill_agent():
    lane_agents = build_lane_agents(
        ["claude", "codex"],
        ["coordinator", "codex_spark"],
        {
            "claude": {},
            "codex": {},
            "coordinator": {"can_fill_main_seat": True},
            "codex_spark": {"can_fill_main_seat": True},
        },
        {"claude": {"status": "exhausted"}, "codex": {"status": "available"}},
        {},
        ["codex_spark"],
    )

    assert lane_agents == ["codex_spark", "codex", "coordinator"]
    print("PASS: lane roster promotes active fill agents when a main agent is exhausted")


def test_lane_agents_restore_available_main_agent_and_keep_gemma_lane():
    lane_agents = build_lane_agents(
        ["claude", "codex"],
        ["coordinator", "codex_spark"],
        {
            "claude": {},
            "codex": {},
            "coordinator": {"can_fill_main_seat": True},
            "codex_spark": {"can_fill_main_seat": True},
        },
        {"claude": {"status": "available"}, "codex": {"status": "available"}},
        {},
        ["codex_spark"],
    )

    assert lane_agents == ["claude", "codex", "coordinator"]
    print("PASS: lane roster restores the main agent while keeping Gemma visible")


def test_lane_agents_prefer_direct_fill_agent_when_no_direct_command_is_active():
    lane_agents = build_lane_agents(
        ["claude", "codex"],
        ["codex_spark", "coordinator"],
        {
            "claude": {},
            "codex": {},
            "coordinator": {"can_fill_main_seat": True},
            "codex_spark": {"can_fill_main_seat": True},
        },
        {"claude": {"status": "exhausted"}, "codex": {"status": "available"}},
        {},
        [],
    )

    assert lane_agents == ["codex_spark", "codex", "coordinator"]
    print("PASS: idle lane roster keeps Spark and Gemma visible when Claude is exhausted")


def test_tailnet_bind_guard_accepts_only_tailscale_cgnat_addresses():
    assert is_tailnet_ipv4_host("100.64.0.1") is True
    assert is_tailnet_ipv4_host("100.127.255.254") is True
    assert is_tailnet_ipv4_host("100.128.0.1") is False
    assert is_tailnet_ipv4_host("192.168.1.10") is False
    assert is_tailnet_ipv4_host("chatboks-test.tail000000.ts.net") is False
    print("PASS: tailnet bind guard only accepts Tailscale CGNAT IPv4 hosts")


def test_allowed_bind_host_requires_explicit_tailnet_flag():
    assert is_allowed_bind_host("127.0.0.1") is True
    assert is_allowed_bind_host("localhost") is True
    assert is_allowed_bind_host("100.64.0.1") is False
    assert is_allowed_bind_host("100.64.0.1", allow_tailnet_bind=True) is True
    assert is_allowed_bind_host("0.0.0.0", allow_tailnet_bind=True) is False
    print("PASS: non-loopback bind requires explicit safe tailnet flag")


def test_allowed_app_origin_accepts_localhost_with_optional_ports():
    assert is_allowed_app_origin("capacitor://localhost") is True
    assert is_allowed_app_origin("http://localhost") is True
    assert is_allowed_app_origin("http://localhost:12345") is True
    assert is_allowed_app_origin("https://127.0.0.1:54321") is True
    assert is_allowed_app_origin("http://evil.example") is False
    assert is_allowed_app_origin("http://chatboks-test.tail000000.ts.net:8765") is False
    print("PASS: app origin guard accepts local app origins but rejects remote web origins")


def test_remote_bridge_rejects_missing_bearer_token():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        try:
            urllib.request.urlopen(f"{base}/api/session", timeout=5)
            assert False, "expected auth failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge requires a bearer token")


def test_remote_bridge_accepts_token_and_forwards_commands():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/session?cursor=7",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["project"] == "chatboks"
        assert "criteria_gate" in payload
        assert payload["events"][0]["id"] == 8

        command = urllib.request.Request(
            f"{base}/api/command",
            data=json.dumps({"text": "@coordinator role call"}).encode("utf-8"),
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(command, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "active"
        assert session.commands == ["@coordinator role call"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge accepts an authorized command and forwards it")


def test_remote_bridge_returns_project_aware_command_completions():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        query = urllib.parse.quote("/mode br", safe="")
        request = urllib.request.Request(
            f"{base}/api/completions?q={query}",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert session.completion_queries == ["/mode br"]
        assert payload["options"] == [
            {"replacement": "/mode brainstorm", "label": "Brainstorm mode"}
        ]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge returns command completion options")


def test_remote_session_command_completions_use_shared_project_catalog():
    session = RemoteSession.__new__(RemoteSession)
    session.app = SimpleNamespace(
        config={"agents": {"claude": {}, "codex": {}}},
        proj_config={"agents": ["claude", "codex"], "direct_agents": ["coordinator"]},
        list_native_skills=lambda: [("implement", "implementation workflow")],
    )

    assert session.command_completions("/session st")["options"] == [
        {"replacement": "/session start", "label": "run DasDashboard start checks"}
    ]
    assert session.command_completions("/skills im")["options"] == [
        {"replacement": "/skills implement", "label": "implementation workflow"}
    ]
    assert session.command_completions("@co")["options"] == [
        {"replacement": "@codex", "label": "route directly to agent"}
    ]


def test_remote_bridge_starts_new_task_for_authorized_client():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/session/new-task",
            data=b"{}",
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "idle"
        assert payload["active_task"] is None
        assert session.commands == ["/new-task"]
        assert payload["events"][0]["text"] == "New task ready."
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge starts a new task for an authorized client")


def test_remote_bridge_rejects_invalid_session_query():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/session?cursor=abc",
            headers={"Authorization": "Bearer secret-token"},
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            assert False, "expected bad query failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
        assert payload["error"] == "Query parameter 'cursor' must be an integer."
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge rejects malformed session query parameters")


def test_remote_bridge_clamps_session_transcript_limit():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/session?cursor=3&limit=999999",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5):
            pass
        assert session.snapshot_calls[-1] == (3, MAX_TRANSCRIPT_LIMIT)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge clamps oversized transcript limits")


def test_remote_bridge_accepts_explicit_full_transcript_request():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/session?cursor=4&limit=all",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5):
            pass
        assert session.snapshot_calls[-1] == (4, None)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge explicitly restores the complete transcript")


def test_remote_bridge_rejects_oversized_json_body():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/pair",
            data=b'{"x":"' + b"a" * MAX_JSON_BODY_BYTES + b'"}',
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            assert False, "expected oversized body failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
        assert "exceeds" in payload["error"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge rejects oversized JSON bodies")


def test_remote_bridge_rejects_non_object_json_body():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/pair",
            data=b"[]",
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            assert False, "expected non-object body failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
        assert payload["error"] == "Request body must be a JSON object."
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge rejects JSON bodies that are not objects")


def test_remote_bridge_lists_projects_for_authorized_client():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/projects",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload == {
            "project": "chatboks",
            "projects": ["biosassist", "chatboks"],
            "project_catalog": [
                {"name": "biosassist", "path": "", "agents": [], "direct_agents": [], "primary": ""},
                {"name": "chatboks", "path": "", "agents": [], "direct_agents": [], "primary": ""},
            ],
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge lists projects for authorized clients")


def test_remote_session_project_catalog_exposes_only_picker_metadata():
    session = RemoteSession.__new__(RemoteSession)
    session.app = SimpleNamespace(
        config={
            "projects": {
                "chatboks": {
                    "path": "C:/work/chatboks",
                    "agents": ["claude", "codex"],
                    "direct_agents": ["coordinator"],
                    "primary": "codex",
                    "secret": "must not leave config",
                }
            }
        }
    )

    assert session.project_catalog() == [
        {
            "name": "chatboks",
            "path": "C:/work/chatboks",
            "agents": ["claude", "codex"],
            "direct_agents": ["coordinator"],
            "primary": "codex",
        }
    ]
    print("PASS: project catalog exposes safe metadata for graphical pickers")


def test_remote_session_register_project_persists_a_local_folder(tmp_path: Path):
    import yaml

    config_path = tmp_path / "config.yaml"
    config_path.write_text("projects: {}\nagents:\n  claude: {}\n  codex: {}\n", encoding="utf-8")
    project_path = tmp_path / "My Projects"
    project_path.mkdir()
    first_project = project_path / "First Project"
    first_project.mkdir()
    (first_project / ".git").mkdir()
    second_project = project_path / "Second Project"
    second_project.mkdir()
    (second_project / "package.json").write_text("{}", encoding="utf-8")
    session = RemoteSession.__new__(RemoteSession)
    session.lock = threading.RLock()
    session.config_path = config_path
    session.app = SimpleNamespace(config=yaml.safe_load(config_path.read_text(encoding="utf-8")))

    created = session.register_project(str(project_path))
    duplicate = session.register_project(str(project_path))
    stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert created == {"projects": ["first-project", "second-project"], "created": ["first-project", "second-project"], "existing": []}
    assert duplicate == {"projects": ["first-project", "second-project"], "created": [], "existing": ["first-project", "second-project"]}
    assert stored["projects"]["first-project"]["path"] == str(first_project.resolve())
    assert stored["projects"]["second-project"]["agents"] == ["claude", "codex"]
    print("PASS: project picker imports a local project folder without duplicate entries")


def test_remote_model_choices_hide_unsupported_codex_chatgpt_account_model():
    assert "gpt-5.6" not in MODEL_CHOICES["codex"]
    assert "gpt-5.6-sol" not in MODEL_CHOICES["codex"]
    assert "gpt-5.5" in MODEL_CHOICES["codex"]
    assert normalize_agent_model("codex", "gpt-5.6") == "gpt-5.5"
    assert normalize_agent_model("codex", "gpt-5.6-sol") == "gpt-5.5"
    print("PASS: remote model picker maps unsupported Codex 5.6 models to GPT-5.5")


def test_remote_session_set_agent_model_persists_normalized_codex_choice(tmp_path: Path):
    import yaml

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "projects: {}\nagents:\n  claude: {}\n  codex: {}\n",
        encoding="utf-8",
    )
    session = RemoteSession.__new__(RemoteSession)
    session.lock = threading.RLock()
    session.config_path = config_path
    session._command_thread = None
    session.events = RemoteEventBuffer()
    session.app = SimpleNamespace(config=yaml.safe_load(config_path.read_text(encoding="utf-8")))
    session.snapshot = lambda cursor=0: {"model_selection": session.model_selection()}  # type: ignore[method-assign]

    payload = session.set_agent_model("codex", "gpt-5.6")
    stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert stored["agents"]["codex"]["model"] == "gpt-5.5"
    assert payload["model_selection"]["codex"]["current"] == "gpt-5.5"
    assert session.events.since(0)[-1]["text"].endswith("Unsupported gpt-5.6 was mapped automatically.")
    print("PASS: remote model picker persists normalized Codex model choices")


def test_remote_session_remove_project_updates_only_the_registry(tmp_path: Path):
    import yaml

    config_path = tmp_path / "config.yaml"
    project_path = tmp_path / "Removable"
    project_path.mkdir()
    config_path.write_text(
        "projects:\n  active:\n    path: .\n  removable:\n    path: " + str(project_path) + "\nagents: {}\n",
        encoding="utf-8",
    )
    session = RemoteSession.__new__(RemoteSession)
    session.lock = threading.RLock()
    session.config_path = config_path
    session.project = "active"
    session._command_thread = None
    session.app = SimpleNamespace(config=yaml.safe_load(config_path.read_text(encoding="utf-8")))

    result = session.remove_project("removable")
    stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert result == {"removed": "removable", "projects": ["active"]}
    assert "removable" not in stored["projects"]
    assert project_path.is_dir()
    print("PASS: project removal only changes the ChatBoks registry")


def test_remote_bridge_switches_project_for_authorized_client():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/project",
            data=json.dumps({"project": "biosassist"}).encode("utf-8"),
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["project"] == "biosassist"
        assert session.project == "biosassist"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge switches projects for authorized clients")


def test_remote_session_snapshot_returns_while_command_is_running(tmp_path: Path):
    started = threading.Event()
    release = threading.Event()
    session = RemoteSession.__new__(RemoteSession)
    session.project = "chatboks"
    session.config_path = None
    session.lock = threading.RLock()
    session._command_thread = None
    session._command_text = None
    session.events = RemoteEventBuffer()
    session.app = BlockingFakeApp(tmp_path / "chatboks.md", started, release)

    try:
        payload = session.submit("@codex slow task")
        assert payload["command_running"] is True
        assert payload["command_text"] == "@codex slow task"
        assert started.wait(timeout=1)

        before = time.monotonic()
        snapshot = session.snapshot()
        elapsed = time.monotonic() - before
        assert elapsed < 0.5
        assert snapshot["command_running"] is True
        assert snapshot["active_task"] == "@codex slow task"
    finally:
        release.set()
        if session._command_thread is not None:
            session._command_thread.join(timeout=5)
    print("PASS: remote session snapshots remain responsive during long commands")


def test_remote_session_does_not_reload_stale_state_during_command(tmp_path: Path):
    started = threading.Event()
    release = threading.Event()
    session = RemoteSession.__new__(RemoteSession)
    session.project = "chatboks"
    session.config_path = None
    session.lock = threading.RLock()
    session._command_thread = None
    session._command_text = None
    session.events = RemoteEventBuffer()
    app = BlockingFakeApp(tmp_path / "chatboks.md", started, release)
    app.state["collaboration_mode"] = "implement"
    load_calls = 0

    def stale_load_state() -> dict[str, object]:
        nonlocal load_calls
        load_calls += 1
        return {**app.state, "collaboration_mode": "brainstorm"}

    app.load_state = stale_load_state  # type: ignore[method-assign]
    session.app = app

    try:
        payload = session.submit("@codex slow task")
        assert started.wait(timeout=1)
        assert payload["collaboration_mode"] == "implement"
        assert session.snapshot()["collaboration_mode"] == "implement"
        assert load_calls == 0
    finally:
        release.set()
        if session._command_thread is not None:
            session._command_thread.join(timeout=5)
    print("PASS: active command state cannot be replaced by a stale disk snapshot")


def test_remote_session_applies_mode_commands_before_returning_snapshot(tmp_path: Path):
    session = RemoteSession.__new__(RemoteSession)
    session.project = "chatboks"
    session.config_path = None
    session.lock = threading.RLock()
    session._command_thread = None
    session._command_text = None
    session.events = RemoteEventBuffer()
    app = BlockingFakeApp(tmp_path / "chatboks.md", threading.Event(), threading.Event())
    app.state["collaboration_mode"] = "brainstorm"

    def apply_mode(text: str) -> None:
        assert text == "/mode implement"
        app.state["collaboration_mode"] = "implement"

    app.handle_user_input = apply_mode  # type: ignore[method-assign]
    session.app = app

    payload = session.submit("/mode implement")

    assert is_collaboration_mode_command("/mode implement") is True
    assert is_collaboration_mode_command("/default") is True
    assert is_collaboration_mode_command("implement") is False
    assert payload["collaboration_mode"] == "implement"
    assert payload["command_running"] is False
    assert session._command_thread is None
    assert "Waiting for agents" not in session.events.since(0)[-1]["text"]
    print("PASS: mode commands update the desktop snapshot synchronously")


def test_remote_session_snapshot_includes_compact_proposal(tmp_path: Path):
    session = RemoteSession.__new__(RemoteSession)
    session.project = "chatboks"
    session.config_path = None
    session.lock = threading.RLock()
    session._command_thread = None
    session._command_text = None
    session.events = RemoteEventBuffer()
    app = BlockingFakeApp(tmp_path / "chatboks.md", threading.Event(), threading.Event())
    app.state["proposal"] = {
        "id": "prop_1",
        "summary": "Ship the remote polish",
        "raw": "Ship the remote polish\n>>> PROPOSAL",
        "proposed_by": "codex",
        "execution_estimate": {"total_tokens": 1200},
        "candidates": [
            {"agent": "claude", "summary": "Review the architecture", "raw": "Claude plan"},
            {"agent": "codex", "summary": "Implement the change", "raw": "Codex plan"},
        ],
    }
    session.app = app

    payload = session.snapshot()

    assert payload["proposal"]["id"] == "prop_1"
    assert payload["proposal"]["summary"] == "Ship the remote polish"
    assert payload["proposal"]["proposed_by"] == "codex"
    assert payload["proposal"]["execution_estimate"] == {"total_tokens": 1200}
    assert [candidate["agent"] for candidate in payload["proposal"]["candidates"]] == ["claude", "codex"]
    assert payload["proposal"]["candidates"][1]["raw"] == "Codex plan"
    print("PASS: remote session snapshots include compact proposal metadata")


def test_remote_session_snapshot_includes_handoff_metadata(tmp_path: Path):
    session = RemoteSession.__new__(RemoteSession)
    session.project = "chatboks"
    session.config_path = None
    session.lock = threading.RLock()
    session._command_thread = None
    session._command_text = None
    session.events = RemoteEventBuffer()
    app = BlockingFakeApp(tmp_path / "chatboks.md", threading.Event(), threading.Event())
    app.state.update({
        "last_agent": "claude",
        "next_agent": "codex",
        "handoff_to": "codex",
        "handoff_reason": "Implementation is ready.",
    })
    session.app = app

    payload = session.snapshot()

    assert payload["handoff_to"] == "codex"
    assert payload["handoff_reason"] == "Implementation is ready."
    print("PASS: remote session snapshots expose handoff metadata")


def test_remote_session_snapshot_includes_trace_payload(tmp_path: Path):
    session = RemoteSession.__new__(RemoteSession)
    session.project = "chatboks"
    session.config_path = None
    session.lock = threading.RLock()
    session._command_thread = None
    session._command_text = None
    session.events = RemoteEventBuffer()
    app = BlockingFakeApp(tmp_path / "chatboks.md", threading.Event(), threading.Event())
    app.chatboks_md.write_text("[CLAUDE] Ready.\n>>> HANDOFF >> Codex\n", encoding="utf-8")
    app.packet_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-12T09:30:00",
                "round": 2,
                "context": {},
                "packet": {
                    "agent": "claude",
                    "stance": "ADD",
                    "observed": ["handoff queued"],
                    "risks": [],
                    "next_action": "Codex implements",
                    "signal": "HANDOFF",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    session.app = app

    payload = session.snapshot()

    assert payload["trace"]["agent"][0]["signal"] == "HANDOFF"
    assert payload["trace"]["agent"][0]["target"] == "Codex"
    assert payload["trace"]["packets"][0]["agent"] == "claude"
    assert payload["trace"]["packets"][0]["observed_count"] == 1
    print("PASS: remote session snapshots include agent and packet trace payloads")


def test_proposal_snapshot_truncates_large_raw_text():
    payload = proposal_snapshot({"raw": "x" * 5000})

    assert payload is not None
    assert len(payload["raw"]) == 4000
    assert payload["raw_truncated"] is True
    print("PASS: proposal snapshots cap raw proposal text")


def test_remote_bridge_allows_capacitor_origin_preflight():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/command",
            method="OPTIONS",
            headers={
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "POST",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == "capacitor://localhost"
            assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
            assert response.headers["X-Frame-Options"] == "DENY"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge allows the Capacitor app origin")


def test_remote_bridge_rejects_untrusted_origin():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/session",
            headers={
                "Origin": "https://evil.example",
                "Authorization": "Bearer secret-token",
            },
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            assert False, "expected origin failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge rejects untrusted web origins")


def test_remote_bridge_pairs_device_and_accepts_short_lived_session_token():
    session = FakeSession()
    server, thread, base = run_server(session, "secret-token")
    try:
        pair_code, _ttl = server.auth.current_pair_code()
        pair_request = urllib.request.Request(
            f"{base}/api/pair",
            data=json.dumps({"pair_code": pair_code}).encode("utf-8"),
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(pair_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ttl_seconds"] > 0
        session_token = payload["session_token"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"

        command = urllib.request.Request(
            f"{base}/api/command",
            data=json.dumps({"text": "/agent"}).encode("utf-8"),
            headers={
                "Origin": "capacitor://localhost",
                "Authorization": f"Bearer {session_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(command, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "active"
        assert session.commands == ["/agent"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge pairs a device and accepts the issued session token")


def test_remote_bridge_rejects_invalid_pair_code():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        pair_request = urllib.request.Request(
            f"{base}/api/pair",
            data=json.dumps({"pair_code": "BADCODE"}).encode("utf-8"),
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(pair_request, timeout=5)
            assert False, "expected pairing failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge rejects invalid pairing codes")


def test_remote_auth_rate_limits_repeated_invalid_pair_codes():
    auth = RemoteAuth("admin-token")

    for _ in range(PAIR_FAILURE_LIMIT - 1):
        assert auth.exchange_pair_code("BADCODE", "127.0.0.1") is None

    with pytest.raises(PairingRateLimited):
        auth.exchange_pair_code("BADCODE", "127.0.0.1")

    with pytest.raises(PairingRateLimited):
        auth.exchange_pair_code(auth.current_pair_code()[0], "127.0.0.1")


def test_remote_bridge_invalidates_pair_code_after_successful_exchange():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        pair_code, _ttl = server.auth.current_pair_code()
        request = urllib.request.Request(
            f"{base}/api/pair",
            data=json.dumps({"pair_code": pair_code}).encode("utf-8"),
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5):
            pass
        try:
            urllib.request.urlopen(request, timeout=5)
            assert False, "expected reused pair code to fail"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge invalidates a pairing code after one successful exchange")


def test_remote_bridge_pair_exchange_updates_operator_file(tmp_path: Path):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        server.write_operator_status()
        original = json.loads(operator_file.read_text(encoding="utf-8"))
        pair_request = urllib.request.Request(
            f"{base}/api/pair",
            data=json.dumps({"pair_code": original["pair_code"]}).encode("utf-8"),
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(pair_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        stored = json.loads(operator_file.read_text(encoding="utf-8"))
        current_code, _ttl = server.auth.current_pair_code()
        assert payload["session_token"]
        assert stored["pair_code"] == current_code
        assert stored["pair_code"] != original["pair_code"]
        assert stored["base_url"] == base
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge updates the operator file after pairing")


def test_remote_bridge_admin_status_reports_running_bridge(tmp_path: Path):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        request = urllib.request.Request(
            f"{base}/api/admin/status",
            headers={"Authorization": "Bearer admin-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "running"
        assert payload["base_url"] == base
        assert payload["project"] == "chatboks"
        assert payload["pid"]
        assert "pair_code" in payload
        assert "admin_token" not in payload
        stored = json.loads(operator_file.read_text(encoding="utf-8"))
        assert stored["base_url"] == base
        assert stored["admin_token"] == "admin-token"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge admin status reports the running bridge")


def test_remote_workbench_reports_bridge_health_without_secrets(tmp_path: Path):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        server.write_operator_status()
        session_token, _ttl = server.auth.exchange_pair_code(server.auth.current_pair_code()[0])
        request = urllib.request.Request(
            f"{base}/api/workbench",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        bridge = payload["bridge"]
        assert bridge["status"] == "running"
        assert bridge["base_url"] == base
        assert bridge["pid"]
        assert bridge["operator_file_exists"] is True
        assert bridge["pair_code_ttl_seconds"] >= 0
        assert "pair_code" not in bridge
        assert "admin_token" not in bridge
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: workbench reports bridge health without exposing operator secrets")


def test_operator_file_guard_rejects_active_bridge(tmp_path: Path):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, _base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        server.write_operator_status()
        try:
            ensure_operator_file_available(operator_file)
            assert False, "expected active bridge guard failure"
        except RuntimeError as exc:
            assert "already owns" in str(exc)
            assert str(operator_file) in str(exc)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: operator file guard rejects a live bridge owner")


def test_operator_file_guard_ignores_stale_operator_file(tmp_path: Path, capsys):
    operator_file = tmp_path / "remote_bridge.json"
    operator_file.write_text(
        json.dumps({"base_url": "http://127.0.0.1:1", "admin_token": "stale-token"}),
        encoding="utf-8",
    )

    ensure_operator_file_available(operator_file)

    output = capsys.readouterr().out
    assert "Ignoring stale remote bridge operator file" in output
    assert "no bridge answered" in output
    assert not operator_file.exists()
    print("PASS: operator file guard ignores unreachable stale metadata")


def test_remote_bridge_server_close_removes_operator_file(tmp_path: Path):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, _base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        server.write_operator_status()
        assert operator_file.exists()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert not operator_file.exists()
    print("PASS: remote bridge removes the operator file on normal shutdown")


def test_remote_bridge_admin_can_rotate_pair_code_and_update_operator_file(tmp_path: Path):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        server.write_operator_status()
        original_code, _ttl = server.auth.current_pair_code()

        rotate_request = urllib.request.Request(
            f"{base}/api/admin/pair-code",
            data=b"{}",
            headers={
                "Authorization": "Bearer admin-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(rotate_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["pair_code"] != original_code
        assert payload["ttl_seconds"] > 0
        stored = json.loads(operator_file.read_text(encoding="utf-8"))
        assert stored["pair_code"] == payload["pair_code"]
        assert stored["admin_token"] == "admin-token"
        assert stored["base_url"] == base
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge admin can rotate pairing code and update operator file")


def test_remote_bridge_session_token_cannot_rotate_pair_code():
    server, thread, base = run_server(FakeSession(), "admin-token")
    try:
        pair_code, _ttl = server.auth.current_pair_code()
        pair_request = urllib.request.Request(
            f"{base}/api/pair",
            data=json.dumps({"pair_code": pair_code}).encode("utf-8"),
            headers={
                "Origin": "capacitor://localhost",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(pair_request, timeout=5) as response:
            session_token = json.loads(response.read().decode("utf-8"))["session_token"]

        rotate_request = urllib.request.Request(
            f"{base}/api/admin/pair-code",
            data=b"{}",
            headers={
                "Authorization": f"Bearer {session_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(rotate_request, timeout=5)
            assert False, "expected session token to be rejected for admin rotation"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: session tokens cannot rotate bridge pairing codes")


def test_remote_bridge_serves_static_ui_files():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert "Content-Security-Policy" in response.headers
            assert "app.js" in body
            assert 'id="eventsPanel" class="panel events-panel hidden"' in body
            assert 'id="bridgeEventsButton"' in body

        with urllib.request.urlopen(f"{base}/app.js", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/javascript")
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert "function visibleTranscript" in body
            assert "function renderSystemControls" in body
            assert "function criteriaGateResponseItems" in body
            assert "Bridge response was unclear. Session refreshed." in body
            assert "function setRefreshState" in body
            assert "Refreshing session..." in body
            assert "function setEventsPanelCollapsed" in body
            assert "function isAgentResponseEvent" in body
            assert "Waiting for agent response..." in body

        with urllib.request.urlopen(f"{base}/styles.css", timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/css")

        with urllib.request.urlopen(f"{base}/favicon.ico", timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("image/png")

        with urllib.request.urlopen(f"{base}/assets/spark.png", timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("image/png")
            assert int(response.headers["Content-Length"]) > 0

        with urllib.request.urlopen(f"{base}/workbench", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert "Content-Security-Policy" in response.headers
            assert "workbench.js" in body
            assert "composerExpandButton" in body
            assert "attentionToggleButton" in body
            assert "activePromptText" in body
            assert "commandCompletionPalette" in body
            assert 'id="laneTabs"' in body
            assert 'id="compareButton"' in body
            assert 'id="handoffBar"' in body

        with urllib.request.urlopen(f"{base}/workbench.js", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/javascript")
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert "updateLaneScrollState" in body
            assert "New task ready" in body
            assert "copyButtonFor" in body
            assert "Copy this response" in body
            assert "message-card-tools" in body
            assert "if (!user && body)" in body
            assert "activePromptFromSession" in body
            assert "renderActivePrompt(cleaned)" in body
            assert "laneTranscriptForSession" in body
            assert "function setComposerHeight" in body
            assert "function setAttentionCollapsed" in body
            assert "return transcript;" in body
            assert 'HISTORY_RESTORE_QUERY = "all"' in body
            assert "theme: state.theme" in body
            assert "updateCommandCompletions" in body
            assert "selectCommandCompletion" in body
            assert 'event.key === "Tab"' in body
            assert "lane-prompt-pip" in body
            assert "function mergeTranscript" in body
            assert "function setLaneView" in body
            assert "function setActiveLane" in body
            assert "function applyResponsiveMode" in body
            assert "function renderHandoff" in body
            assert "function renderHandoffIdentity" in body
            assert "handoffTransition" in body
            assert "explicitHandoffChanged" in body
            assert "scrollIntoView" in body
            assert 'event.key === "ArrowRight"' in body

        with urllib.request.urlopen(f"{base}/workbench.css", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "body.is-compact-workbench" in body
            assert "height: 100dvh" in body
            assert "overflow-wrap: anywhere" in body

        with urllib.request.urlopen(f"{base}/workbench.css", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/css")
            assert "lane-jump-button" in body
            assert "status-confirm-flash" in body
            assert "card-copy-button" in body
            assert "message-card-tools" in body
            assert "active-prompt-card" in body
            assert "lane-prompt-nav" in body
            assert "history-search" in body
            assert '.agent-lanes[data-view="task"]' in body
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge serves the mobile and workbench static UI files")


def test_remote_bridge_rejects_paths_outside_static_allowlist():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        for path in (
            "/assets/../remote_control.py",
            "/index.html",
            "/workbench.html",
            "/assets/unknown.png",
            "/../config.yaml",
        ):
            try:
                urllib.request.urlopen(f"{base}{path}", timeout=5)
                assert False, f"expected 404 for {path}"
            except urllib.error.HTTPError as exc:
                assert exc.code == 404, f"expected 404 for {path}, got {exc.code}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge serves only the exact static allowlist")


def test_workbench_api_requires_token_and_returns_status():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        try:
            urllib.request.urlopen(f"{base}/api/workbench", timeout=5)
            assert False, "expected auth failure"
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        request = urllib.request.Request(
            f"{base}/api/workbench",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["project"] == "chatboks"
        assert payload["environment"]["branch"] == "main"
        assert payload["graph"]["files"] == 52
        assert "monitor" in payload
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: workbench status API requires a token and returns structured status")


def test_build_token_usage_orders_main_agents_and_computes_percent():
    usage = build_token_usage(
        {"codex": 60_000, "coordinator": 500},
        {
            "claude": {"token_limit": 180_000, "token_warning": 150_000},
            "codex": {"token_limit": 120_000, "token_warning": 100_000},
        },
        ["claude", "codex"],
    )

    assert [entry["agent"] for entry in usage] == ["claude", "codex", "coordinator"]
    assert usage[0] == {"agent": "claude", "used": 0, "limit": 180_000, "warning": 150_000, "percent": 0.0}
    assert usage[1]["percent"] == 50.0
    assert usage[2]["percent"] is None
    print("PASS: token usage payload keeps roster order and computes percentages")


def test_git_environment_returns_none_for_non_repo(tmp_path: Path):
    assert git_environment(None) is None
    assert git_environment(tmp_path) is None
    print("PASS: git environment is fail-soft outside a repository")


def test_codegraph_stats_reads_counts_from_database(tmp_path: Path):
    import sqlite3

    assert codegraph_stats(None) is None
    assert codegraph_stats(tmp_path) is None

    db_dir = tmp_path / ".codegraph"
    db_dir.mkdir()
    connection = sqlite3.connect(db_dir / "codegraph.db")
    connection.executescript(
        """
        CREATE TABLE files (path TEXT);
        CREATE TABLE nodes (id INTEGER);
        CREATE TABLE edges (id INTEGER);
        INSERT INTO files VALUES ('a.py'), ('b.py');
        INSERT INTO nodes VALUES (1), (2), (3);
        INSERT INTO edges VALUES (1);
        """
    )
    connection.commit()
    connection.close()

    stats = codegraph_stats(tmp_path)

    assert stats is not None
    assert stats["healthy"] is True
    assert stats["files"] == 2
    assert stats["nodes"] == 3
    assert stats["edges"] == 1
    assert stats["last_indexed"]
    print("PASS: codegraph stats read counts from the index database")


def test_find_codegraph_command_uses_npm_bin_when_path_is_missing(tmp_path: Path):
    import remote_control as remote
    from unittest.mock import patch

    npm_bin = tmp_path / "npm"
    npm_bin.mkdir()
    command = npm_bin / "codegraph.cmd"
    command.write_text("@echo off\n", encoding="utf-8")

    with patch.object(remote.shutil, "which", return_value=None), patch.dict(remote.os.environ, {"APPDATA": str(tmp_path)}):
        assert remote.find_codegraph_command() == str(command)
    print("PASS: CodeGraph lookup finds npm's global command outside PATH")


def test_register_project_path_disables_codegraph_by_default(tmp_path: Path):
    projects: dict[str, object] = {}

    name, created = RemoteSession.register_project_path(projects, tmp_path / "NewProject", ["codex"])

    assert created is True
    assert projects[name]["codegraph"] is False
    print("PASS: new projects do not start CodeGraph automatically")


def test_configure_active_codegraph_skips_disabled_project(tmp_path: Path):
    session = RemoteSession.__new__(RemoteSession)
    session.lock = threading.RLock()
    session.app = SimpleNamespace(
        project="no-graph",
        proj_path=str(tmp_path),
        proj_config={"codegraph": False},
    )
    session._codegraph_process = None
    session._codegraph_project = None
    session._codegraph_generation = 0
    session._codegraph_state = {"status": "idle", "enabled": False}
    session._workbench_cache = (1.0, {"graph": {"status": "indexing"}})

    session.configure_active_codegraph()

    assert session._codegraph_process is None
    assert session._codegraph_state == {"status": "disabled", "enabled": False, "project": "no-graph"}
    assert session._workbench_cache is None
    print("PASS: disabled projects do not launch CodeGraph")


def test_rotate_pair_code_helper_uses_operator_file(tmp_path: Path, capsys):
    operator_file = tmp_path / "remote_bridge.json"
    server, thread, base = run_server(FakeSession(), "admin-token", operator_file)
    try:
        server.write_operator_status()

        result = rotate_pair_code_from_operator_file(operator_file)

        output = capsys.readouterr().out
        stored = json.loads(operator_file.read_text(encoding="utf-8"))
        assert result == 0
        assert f"Bridge URL: {base}" in output
        assert stored["pair_code"] in output
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: rotate-pair-code helper uses the operator file")


def test_rotate_pair_code_helper_reports_stale_operator_file(tmp_path: Path, capsys):
    operator_file = tmp_path / "remote_bridge.json"
    operator_file.write_text(
        json.dumps({"base_url": "http://127.0.0.1:1", "admin_token": "stale-token"}),
        encoding="utf-8",
    )

    result = rotate_pair_code_from_operator_file(operator_file)

    output = capsys.readouterr().out
    assert result == 1
    assert "Stale remote bridge operator file" in output
    assert "Start the bridge again" in output
    print("PASS: rotate-pair-code helper reports stale operator files clearly")
