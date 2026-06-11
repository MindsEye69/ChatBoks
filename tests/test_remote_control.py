from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from remote_control import (
    RemoteEventBuffer,
    RemoteAuth,
    RemoteBridgeServer,
    RemoteHandler,
    RemoteSession,
    is_allowed_bind_host,
    is_allowed_app_origin,
    is_tailnet_ipv4_host,
    parse_chatboks_messages,
    rotate_pair_code_from_operator_file,
)


class FakeSession:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.project = "chatboks"
        self.projects = ["biosassist", "chatboks"]

    def snapshot(self, cursor: int = 0, transcript_limit: int = 120) -> dict[str, object]:
        del transcript_limit
        return {
            "project": self.project,
            "projects": self.projects,
            "status": "active",
            "active_task": "test",
            "next_agent": "codex",
            "token_line": "session tokens: CODEX 1.0k/120k",
            "transcript": [{"id": 0, "sender": "you", "text": "hello"}],
            "events": [{"id": cursor + 1, "sender": "system", "text": "ok"}],
        }

    def submit(self, text: str) -> dict[str, object]:
        self.commands.append(text)
        return self.snapshot()

    def available_projects(self) -> list[str]:
        return self.projects

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
    print("PASS: remote transcript parsing keeps multiline turns intact")


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
        assert payload["events"][0]["id"] == 8

        command = urllib.request.Request(
            f"{base}/api/command",
            data=json.dumps({"text": "@zero role call"}).encode("utf-8"),
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(command, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "active"
        assert session.commands == ["@zero role call"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge accepts an authorized command and forwards it")


def test_remote_bridge_lists_projects_for_authorized_client():
    server, thread, base = run_server(FakeSession(), "secret-token")
    try:
        request = urllib.request.Request(
            f"{base}/api/projects",
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload == {"project": "chatboks", "projects": ["biosassist", "chatboks"]}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    print("PASS: remote bridge lists projects for authorized clients")


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
