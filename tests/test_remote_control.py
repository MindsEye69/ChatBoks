from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from remote_control import RemoteAuth, RemoteBridgeServer, RemoteHandler, parse_chatboks_messages


class FakeSession:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def snapshot(self, cursor: int = 0, transcript_limit: int = 120) -> dict[str, object]:
        del transcript_limit
        return {
            "project": "chatboks",
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


def run_server(session: FakeSession, token: str) -> tuple[RemoteBridgeServer, threading.Thread, str]:
    server = RemoteBridgeServer(("127.0.0.1", 0), RemoteHandler, session, RemoteAuth(token))
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
