#!/usr/bin/env python3
"""Mobile-friendly remote control bridge for a local ChatBoks session.

The bridge is intentionally conservative:
- Binds to loopback only by default.
- Requires an explicit bearer token for API access.
- Keeps ChatBoks execution local to the desktop that owns the repo.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import secrets
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from context.transcript import is_transcript_turn
from encoding_utils import configure_utf8_stdio
from orchestrator import Chatboks
from ui.stream import Stream


TRANSCRIPT_LIMIT = 120
COMMAND_MAX_CHARS = 6000
PAIR_CODE_LENGTH = 8
PAIR_CODE_TTL_SECONDS = 300
SESSION_TOKEN_TTL_SECONDS = 8 * 60 * 60
ALLOWED_APP_ORIGINS = {
    "capacitor://localhost",
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
}
SHELL_CSP = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}


def is_tailnet_ipv4_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError:
        return False
    return address.version == 4 and address in ipaddress.ip_network("100.64.0.0/10")


def is_allowed_bind_host(host: str, allow_tailnet_bind: bool = False) -> bool:
    if is_loopback_host(host):
        return True
    return allow_tailnet_bind and is_tailnet_ipv4_host(host)


def is_allowed_app_origin(origin: str) -> bool:
    normalized = origin.strip().lower()
    if normalized in ALLOWED_APP_ORIGINS:
        return True
    parsed = urllib.parse.urlparse(normalized)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"localhost", "127.0.0.1"}


def parse_chatboks_messages(path: Path, limit: int = TRANSCRIPT_LIMIT) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if lines[:1] == ["---"]:
        try:
            second = lines.index("---", 1)
            lines = lines[second + 1 :]
        except ValueError:
            lines = lines[1:]

    messages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            if current is not None and current["text"]:
                current["text"] += "\n"
            continue
        if is_transcript_turn(line):
            tag, _, remainder = line.partition("]")
            sender = tag.lstrip("[").strip().lower()
            current = {"sender": sender, "text": remainder.strip()}
            messages.append(current)
            continue
        if current is not None:
            current["text"] += ("\n" if current["text"] else "") + line

    trimmed = []
    for index, message in enumerate(messages[-limit:], start=max(0, len(messages) - limit)):
        trimmed.append({"id": index, "sender": message["sender"], "text": message["text"].strip()})
    return trimmed


class RemoteEventBuffer:
    def __init__(self, max_events: int = 256) -> None:
        self.max_events = max_events
        self._events: list[dict[str, Any]] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def append(self, kind: str, sender: str, text: str) -> None:
        payload = {
            "id": self._next_id,
            "kind": kind,
            "sender": sender,
            "text": text.strip(),
            "timestamp": time.strftime("%H:%M:%S"),
        }
        with self._lock:
            self._next_id += 1
            self._events.append(payload)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]

    def since(self, cursor: int) -> list[dict[str, Any]]:
        with self._lock:
            return [event for event in self._events if int(event["id"]) > cursor]


class RemoteAuth:
    def __init__(self, admin_token: str) -> None:
        self.admin_token = admin_token
        self._lock = threading.Lock()
        self._pair_code = self._new_pair_code()
        self._pair_code_expires_at = time.time() + PAIR_CODE_TTL_SECONDS
        self._session_tokens: dict[str, float] = {}

    def _new_pair_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(PAIR_CODE_LENGTH))

    def current_pair_code(self) -> tuple[str, int]:
        with self._lock:
            self._refresh_pair_code_if_needed()
            remaining = max(0, int(self._pair_code_expires_at - time.time()))
            return self._pair_code, remaining

    def rotate_pair_code(self) -> tuple[str, int]:
        with self._lock:
            self._pair_code = self._new_pair_code()
            self._pair_code_expires_at = time.time() + PAIR_CODE_TTL_SECONDS
            return self._pair_code, PAIR_CODE_TTL_SECONDS

    def exchange_pair_code(self, pair_code: str) -> tuple[str, int] | None:
        normalized = pair_code.strip().upper()
        if not normalized:
            return None
        with self._lock:
            self._refresh_pair_code_if_needed()
            if not secrets.compare_digest(normalized, self._pair_code):
                return None
            token = secrets.token_urlsafe(32)
            expires_at = time.time() + SESSION_TOKEN_TTL_SECONDS
            self._session_tokens[token] = expires_at
            self._pair_code = self._new_pair_code()
            self._pair_code_expires_at = time.time() + PAIR_CODE_TTL_SECONDS
            return token, SESSION_TOKEN_TTL_SECONDS

    def authorize(self, token: str) -> bool:
        if not token:
            return False
        if secrets.compare_digest(token, self.admin_token):
            return True
        now = time.time()
        with self._lock:
            self._prune_expired_sessions(now)
            expires_at = self._session_tokens.get(token)
            return expires_at is not None and expires_at > now

    def _refresh_pair_code_if_needed(self) -> None:
        now = time.time()
        if now >= self._pair_code_expires_at:
            self._pair_code = self._new_pair_code()
            self._pair_code_expires_at = now + PAIR_CODE_TTL_SECONDS

    def _prune_expired_sessions(self, now: float) -> None:
        expired = [token for token, expires_at in self._session_tokens.items() if expires_at <= now]
        for token in expired:
            self._session_tokens.pop(token, None)


class RemoteStream(Stream):
    def __init__(self, agent_config: dict[str, Any], agents: list[str], events: RemoteEventBuffer) -> None:
        super().__init__(agent_config, agents)
        self.events = events

    def banner(self, project: str) -> None:
        self.events.append("banner", "system", f"CHATBOKS - {project.upper()}")

    def ready(self) -> None:
        self.events.append("status", "system", "Remote bridge ready.")

    def intro(self, project: str) -> None:
        self.events.append("intro", "system", f"Attached to ChatBoks project {project}.")

    def role_call(self, agents: list[str], standby_agents: list[str] | None = None) -> None:
        line = "role call: " + "  ".join(agent.upper() for agent in agents)
        if standby_agents:
            line += "  (standby: " + "  ".join(agent.upper() for agent in standby_agents) + ")"
        self.events.append("role_call", "system", line)

    def message(self, sender: str, text: str, timestamp: str) -> None:
        self.events.append("message", sender.lower(), f"{timestamp}\n{text.strip()}")

    def standby(self, agent_name: str, text: str) -> None:
        self.events.append("standby", agent_name.lower(), text)

    def system(self, text: str) -> None:
        self.events.append("system", "system", text)

    def help_box(self, commands: list[tuple[str, str]]) -> None:
        lines = ["ChatBoks commands:"]
        lines.extend(f"{command} - {description}" for command, description in commands)
        self.events.append("help", "system", "\n".join(lines))

    def proposal(self, text: str) -> None:
        self.events.append("proposal", "system", text)

    def question(self, text: str) -> None:
        self.events.append("question", "system", text)

    def escalate(self, text: str) -> None:
        self.events.append("escalate", "system", text)

    def token_usage(
        self,
        token_counts: dict[str, int],
        session_budget: dict[str, int] | None = None,
    ) -> None:
        self.events.append("usage", "system", self.build_token_usage_line(token_counts, session_budget))

    def prompt(self, label: str = "You > ") -> str:
        raise RuntimeError(f"Remote stream is non-interactive: {label}")


class RemoteSession:
    def __init__(self, project: str, config_path: Path | None = None) -> None:
        self.project = project
        self.config_path = config_path
        self.app = Chatboks(project, trigger="manual", config_path=config_path)
        self.lock = threading.RLock()
        self._command_thread: threading.Thread | None = None
        self._command_text: str | None = None
        self.events = RemoteEventBuffer()
        self.app.stream = RemoteStream(
            self.app.config.get("agents", {}),
            self.app.proj_config["agents"],
            self.events,
        )
        self.prepare()

    def available_projects(self) -> list[str]:
        return sorted((self.app.config.get("projects") or {}).keys())

    def prepare(self) -> None:
        with self.lock:
            self.app.ensure_project_files()
            if self.app.state.get("status") == "initializing":
                self.app.initialize_agents()
            self.app.stream.ready()
            self.app.refresh_token_usage_display()

    def switch_project(self, project: str) -> dict[str, Any]:
        target = project.strip()
        if not target:
            raise ValueError("Project name cannot be empty.")
        if target not in self.available_projects():
            raise ValueError(f"Unknown project '{target}'.")
        with self.lock:
            if self.command_running():
                raise ValueError("Cannot switch project while a command is running.")
            self.project = target
            self.app = Chatboks(target, trigger="manual", config_path=self.config_path)
            self._command_thread = None
            self._command_text = None
            self.events = RemoteEventBuffer()
            self.app.stream = RemoteStream(
                self.app.config.get("agents", {}),
                self.app.proj_config["agents"],
                self.events,
            )
            self.prepare()
            self.events.append("system", "system", f"Switched remote project to {target}.")
            return self.snapshot(cursor=0)

    def command_running(self) -> bool:
        return self._command_thread is not None and self._command_thread.is_alive()

    def submit(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Command text cannot be empty.")
        if len(cleaned) > COMMAND_MAX_CHARS:
            raise ValueError(f"Command text exceeds {COMMAND_MAX_CHARS} characters.")
        with self.lock:
            if self.command_running():
                raise ValueError("A remote command is already running.")
            self._command_text = cleaned
            self.events.append("system", "system", "Command accepted. Waiting for agents.")
            self._command_thread = threading.Thread(
                target=self._run_command,
                args=(cleaned,),
                daemon=True,
                name="chatboks-remote-command",
            )
            self._command_thread.start()
            return self.snapshot(cursor=0)

    def _run_command(self, text: str) -> None:
        try:
            self.app.handle_user_input(text)
        except Exception as exc:  # noqa: BLE001
            self.events.append("error", "system", f"Remote command failed: {exc}")
        finally:
            with self.lock:
                self._command_text = None

    def snapshot(self, cursor: int = 0, transcript_limit: int = TRANSCRIPT_LIMIT) -> dict[str, Any]:
        with self.lock:
            self.app.state = self.app.load_state()
            context = self.app.state.get("context") or {}
            token_counts = dict(context.get("token_counts") or {})
            token_line = self.app.stream.build_token_usage_line(token_counts, self.app.session_token_budget())
            return {
                "project": self.app.project,
                "projects": self.available_projects(),
                "status": self.app.state.get("status"),
                "active_task": self.app.state.get("active_task"),
                "next_agent": self.app.state.get("next_agent"),
                "last_agent": self.app.state.get("last_agent"),
                "collaboration_mode": self.app.state.get("collaboration_mode"),
                "context_mode": self.app.state.get("context_mode"),
                "command_running": self.command_running(),
                "command_text": self._command_text,
                "token_line": token_line,
                "transcript": parse_chatboks_messages(self.app.chatboks_md, limit=transcript_limit),
                "events": self.events.since(cursor),
            }


class RemoteBridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        session: RemoteSession,
        auth: RemoteAuth,
    ) -> None:
        super().__init__(address, handler)
        self.session = session
        self.auth = auth


class RemoteHandler(BaseHTTPRequestHandler):
    server: RemoteBridgeServer

    def do_OPTIONS(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        origin = self.request_origin()
        if origin and not is_allowed_app_origin(origin):
            self.respond_error(HTTPStatus.FORBIDDEN, "Origin not allowed")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.write_cors_headers(origin)
        self.write_security_headers()
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.respond_html(build_mobile_shell(self.server.session.app.project))
            return
        if parsed.path == "/api/session":
            if not self.origin_allowed():
                return
            if not self.authorized():
                return
            query = urllib.parse.parse_qs(parsed.query)
            cursor = int(query.get("cursor", ["0"])[0] or 0)
            limit = int(query.get("limit", [str(TRANSCRIPT_LIMIT)])[0] or TRANSCRIPT_LIMIT)
            self.respond_json(self.server.session.snapshot(cursor=cursor, transcript_limit=limit))
            return
        if parsed.path == "/api/projects":
            if not self.origin_allowed():
                return
            if not self.authorized():
                return
            self.respond_json(
                {
                    "project": self.server.session.snapshot(cursor=0, transcript_limit=0).get("project"),
                    "projects": self.server.session.available_projects(),
                }
            )
            return
        self.respond_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/pair":
            if not self.origin_allowed():
                return
            try:
                payload = self.read_json_body()
            except ValueError as exc:
                self.respond_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            pair_code = str(payload.get("pair_code") or "")
            result = self.server.auth.exchange_pair_code(pair_code)
            if result is None:
                self.respond_error(HTTPStatus.FORBIDDEN, "Invalid or expired pairing code")
                return
            session_token, ttl = result
            self.respond_json({"session_token": session_token, "ttl_seconds": ttl})
            return
        if parsed.path == "/api/project":
            if not self.origin_allowed():
                return
            if not self.authorized():
                return
            try:
                payload = self.read_json_body()
                snapshot = self.server.session.switch_project(str(payload.get("project") or ""))
            except ValueError as exc:
                self.respond_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self.respond_json(snapshot)
            return
        if parsed.path != "/api/command":
            self.respond_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not self.origin_allowed():
            return
        if not self.authorized():
            return
        try:
            payload = self.read_json_body()
        except ValueError as exc:
            self.respond_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        text = str(payload.get("text") or "")
        try:
            snapshot = self.server.session.submit(text)
        except ValueError as exc:
            self.respond_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.respond_json(snapshot)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        print(f"{self.address_string()} - {format % args}")

    def authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.write_cors_headers(self.request_origin())
            self.send_header("WWW-Authenticate", 'Bearer realm="ChatBoks Remote"')
            self.end_headers()
            return False
        provided = header.removeprefix("Bearer ").strip()
        if not self.server.auth.authorize(provided):
            self.respond_error(HTTPStatus.FORBIDDEN, "Invalid token")
            return False
        return True

    def read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc

    def respond_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.write_cors_headers(self.request_origin())
        self.write_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.write_cors_headers(self.request_origin())
        self.write_security_headers(include_csp=True)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_error(self, status: HTTPStatus, message: str) -> None:
        self.respond_json({"error": message, "status": int(status)}, status=status)

    def request_origin(self) -> str | None:
        origin = (self.headers.get("Origin") or "").strip()
        return origin or None

    def origin_allowed(self) -> bool:
        origin = self.request_origin()
        if origin and not is_allowed_app_origin(origin):
            self.respond_error(HTTPStatus.FORBIDDEN, "Origin not allowed")
            return False
        return True

    def write_cors_headers(self, origin: str | None) -> None:
        if not origin:
            return
        if origin in ALLOWED_APP_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def write_security_headers(self, include_csp: bool = False) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if include_csp:
            self.send_header("Content-Security-Policy", SHELL_CSP)


def build_mobile_shell(project: str) -> str:
    escaped_project = project.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ChatBoks Remote - {escaped_project}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #111214;
      --panel: #191b1f;
      --border: #2a2e35;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --accent: #f97316;
      --accent-2: #22c55e;
      --danger: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(17, 18, 20, 0.94);
      border-bottom: 1px solid var(--border);
      padding: 14px 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
    }}
    .sub {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }}
    main {{
      padding: 16px;
      display: grid;
      gap: 12px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
    }}
    .meta {{
      display: grid;
      gap: 6px;
      font-size: 14px;
    }}
    .meta strong {{
      color: var(--muted);
      font-weight: 600;
    }}
    .tokens {{
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 12px;
      color: var(--muted);
      white-space: pre-wrap;
    }}
    .list {{
      display: grid;
      gap: 10px;
      max-height: 48vh;
      overflow: auto;
    }}
    .item {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #14161a;
    }}
    .sender {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .text {{
      white-space: pre-wrap;
      line-height: 1.4;
      word-break: break-word;
    }}
    textarea, input {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #101215;
      color: var(--text);
      padding: 12px;
      font: inherit;
    }}
    textarea {{
      min-height: 100px;
      resize: vertical;
    }}
    .row {{
      display: grid;
      gap: 10px;
    }}
    button {{
      appearance: none;
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 12px;
      font: inherit;
      color: white;
      background: var(--accent);
    }}
    button.secondary {{
      background: transparent;
      border-color: var(--border);
      color: var(--text);
    }}
    button.inline {{
      padding: 10px;
      font-size: 14px;
    }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }}
    .error {{
      color: #fecaca;
      background: rgba(127, 29, 29, 0.35);
      border: 1px solid rgba(248, 113, 113, 0.4);
      border-radius: 8px;
      padding: 10px;
      display: none;
    }}
    .quick {{
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
  </style>
</head>
<body>
  <header>
    <h1>ChatBoks Remote</h1>
    <div class="sub">{escaped_project} desktop bridge</div>
  </header>
  <main>
    <section>
      <div class="row">
        <input id="pairCode" type="text" placeholder="Enter one-time pairing code" autocomplete="one-time-code">
        <input id="token" type="password" placeholder="Session token (filled after pairing)">
        <div class="quick">
          <button class="secondary inline" id="pair">Pair device</button>
          <button class="secondary inline" id="saveToken">Save token</button>
          <button class="secondary inline" id="refresh">Refresh</button>
        </div>
      </div>
      <p class="hint">Pair with the one-time desktop code first. Session tokens are short-lived; saving one is optional and meant for your own device only.</p>
      <div id="error" class="error"></div>
    </section>

    <section>
      <div class="meta">
        <div><strong>Status:</strong> <span id="status">-</span></div>
        <div><strong>Active task:</strong> <span id="task">-</span></div>
        <div><strong>Next agent:</strong> <span id="next">-</span></div>
      </div>
      <div class="tokens" id="tokens"></div>
    </section>

    <section>
      <div class="quick">
        <button class="secondary inline" data-prompt="@zero role call">Agent Zero role call</button>
        <button class="secondary inline" data-prompt="@zero what's next for ChatBoks?">Ask Zero what's next</button>
      </div>
    </section>

    <section>
      <div class="row">
        <textarea id="prompt" placeholder="Send a prompt or slash command"></textarea>
        <button id="send">Send to ChatBoks</button>
      </div>
    </section>

    <section>
      <div class="sender">Transcript</div>
      <div id="transcript" class="list"></div>
    </section>

    <section>
      <div class="sender">Live bridge events</div>
      <div id="events" class="list"></div>
    </section>
  </main>
  <script>
    const tokenInput = document.getElementById("token");
    const pairCodeInput = document.getElementById("pairCode");
    const errorBox = document.getElementById("error");
    const transcriptBox = document.getElementById("transcript");
    const eventsBox = document.getElementById("events");
    const promptInput = document.getElementById("prompt");
    const statusEl = document.getElementById("status");
    const taskEl = document.getElementById("task");
    const nextEl = document.getElementById("next");
    const tokensEl = document.getElementById("tokens");
    let eventCursor = 0;

    const params = new URLSearchParams(window.location.search);
    tokenInput.value = params.get("token") || localStorage.getItem("chatboks-remote-token") || "";

    function showError(message) {{
      errorBox.style.display = message ? "block" : "none";
      errorBox.textContent = message || "";
    }}

    function authHeaders() {{
      const token = tokenInput.value.trim();
      if (!token) {{
        throw new Error("Enter the bearer token from the desktop bridge first.");
      }}
      return {{
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json"
      }};
    }}

    function renderItems(container, items) {{
      container.innerHTML = "";
      for (const item of items) {{
        const div = document.createElement("div");
        div.className = "item";
        const sender = document.createElement("div");
        sender.className = "sender";
        sender.textContent = item.sender;
        const text = document.createElement("div");
        text.className = "text";
        text.textContent = item.text;
        div.appendChild(sender);
        div.appendChild(text);
        container.appendChild(div);
      }}
    }}

    async function pairDevice() {{
      const code = pairCodeInput.value.trim();
      if (!code) {{
        throw new Error("Enter the one-time pairing code from the desktop bridge.");
      }}
      const response = await fetch("/api/pair", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ pair_code: code }})
      }});
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || "Pairing failed.");
      }}
      tokenInput.value = data.session_token || "";
      pairCodeInput.value = "";
      return data;
    }}

    async function refreshSession() {{
      try {{
        const response = await fetch("/api/session?cursor=" + eventCursor, {{
          headers: authHeaders()
        }});
        if (!response.ok) {{
          throw new Error("Refresh failed: " + response.status);
        }}
        const data = await response.json();
        statusEl.textContent = data.status || "-";
        taskEl.textContent = data.active_task || "-";
        nextEl.textContent = data.next_agent || "-";
        tokensEl.textContent = data.token_line || "";
        renderItems(transcriptBox, data.transcript || []);
        const events = data.events || [];
        if (events.length) {{
          eventCursor = events[events.length - 1].id;
        }}
        renderItems(eventsBox, events);
        showError("");
      }} catch (error) {{
        showError(error.message || String(error));
      }}
    }}

    async function sendPrompt(text) {{
      try {{
        const response = await fetch("/api/command", {{
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({{ text }})
        }});
        const data = await response.json();
        if (!response.ok) {{
          throw new Error(data.error || "Command failed.");
        }}
        promptInput.value = "";
        await refreshSession();
      }} catch (error) {{
        showError(error.message || String(error));
      }}
    }}

    document.getElementById("saveToken").addEventListener("click", () => {{
      localStorage.setItem("chatboks-remote-token", tokenInput.value.trim());
      showError("");
    }});

    document.getElementById("pair").addEventListener("click", async () => {{
      try {{
        await pairDevice();
        showError("");
      }} catch (error) {{
        showError(error.message || String(error));
      }}
    }});

    document.getElementById("refresh").addEventListener("click", refreshSession);

    document.getElementById("send").addEventListener("click", () => {{
      const text = promptInput.value.trim();
      if (text) {{
        sendPrompt(text);
      }}
    }});

    for (const button of document.querySelectorAll("[data-prompt]")) {{
      button.addEventListener("click", () => sendPrompt(button.dataset.prompt));
    }}

    refreshSession();
    setInterval(refreshSession, 3000);
  </script>
</body>
</html>
"""


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Secure remote bridge for ChatBoks")
    parser.add_argument("project", help="Project name from config.yaml")
    parser.add_argument("--config", type=Path, default=None, help="Optional path to ChatBoks config.yaml")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Loopback port for the bridge (default: 8765)")
    parser.add_argument("--token", help="Admin bearer token for API access. Random if omitted.")
    parser.add_argument("--show-admin-token", action="store_true", help="Print the admin token on startup.")
    parser.add_argument(
        "--allow-tailnet-bind",
        action="store_true",
        help="Allow binding to a Tailscale 100.64.0.0/10 IPv4 address when Tailscale Serve is unavailable.",
    )
    args = parser.parse_args()

    if not is_allowed_bind_host(args.host, allow_tailnet_bind=args.allow_tailnet_bind):
        raise SystemExit(
            "Refusing unsafe bind. Use loopback, or pass --allow-tailnet-bind with a Tailscale 100.64.0.0/10 IPv4 address."
        )

    session = RemoteSession(args.project, config_path=args.config)
    admin_token = args.token or secrets.token_urlsafe(24)
    auth = RemoteAuth(admin_token)
    server = RemoteBridgeServer((args.host, args.port), RemoteHandler, session, auth)
    pair_code, pair_ttl = auth.current_pair_code()

    print(f"ChatBoks remote bridge for project '{args.project}'")
    print(f"Listening on http://{args.host}:{args.port}/")
    print("Security defaults:")
    if is_loopback_host(args.host):
        print("- loopback bind only")
    else:
        print("- Tailscale tailnet bind only")
    print("- one-time pairing code issues short-lived session tokens")
    print("- bearer token required on every API request")
    print("- intended remote path: private tunnel such as Tailscale Serve")
    print("")
    print(f"Pairing code: {pair_code} (expires in {pair_ttl} seconds)")
    print(f"Session token lifetime: {SESSION_TOKEN_TTL_SECONDS} seconds")
    if args.show_admin_token:
        print(f"Admin token: {admin_token}")
    else:
        print("Admin token: hidden by default (use --show-admin-token to print it)")
    print("")
    print("Open the URL on the desktop browser, or tunnel it to your phone through a private network.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping remote bridge.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
