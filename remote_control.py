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
import os
import secrets
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from context.packets import packet_records_from_jsonl
from context.transcript import is_transcript_turn
from encoding_utils import configure_utf8_stdio
from orchestrator import DEFAULT_AGENT_FALLBACKS, Chatboks
from ui.stream import Stream


TRANSCRIPT_LIMIT = 120
MAX_TRANSCRIPT_LIMIT = TRANSCRIPT_LIMIT
COMMAND_MAX_CHARS = 6000
REMOTE_PROPOSAL_RAW_LIMIT = 4000
TRACE_SUMMARY_LIMIT = 140
LANE_AGENT_LIMIT = 3
MAX_JSON_BODY_BYTES = 64 * 1024
PAIR_CODE_LENGTH = 8
PAIR_CODE_TTL_SECONDS = 300
SESSION_TOKEN_TTL_SECONDS = 8 * 60 * 60
OPERATOR_STATUS_FILENAME = "remote_bridge.json"
OPERATOR_PROBE_TIMEOUT_SECONDS = 2.0
WORKBENCH_STATUS_CACHE_SECONDS = 5.0
WORKBENCH_WWW_ROOT = Path(__file__).resolve().parent / "mobile_remote" / "www"
# Exact-match allowlist: request paths never touch the filesystem directly,
# so traversal sequences in a URL can only miss the map and return 404.
WORKBENCH_STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/workbench": ("workbench.html", "text/html; charset=utf-8"),
    "/workbench.css": ("workbench.css", "text/css; charset=utf-8"),
    "/workbench.js": ("workbench.js", "text/javascript; charset=utf-8"),
    "/favicon.ico": ("assets/chatboks-mark.png", "image/png"),
    "/assets/chatboks-logo.png": ("assets/chatboks-logo.png", "image/png"),
    "/assets/chatboks-mark.png": ("assets/chatboks-mark.png", "image/png"),
}
ALLOWED_APP_ORIGINS = {
    "capacitor://localhost",
    "http://localhost",
    "https://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
}
AGENT_ALIASES = {
    "agent_zero": "coordinator",
    "agentzero": "coordinator",
    "az": "coordinator",
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
            sender = canonical_agent_name(tag.lstrip("[").strip())
            current = {"sender": sender, "text": remainder.strip()}
            messages.append(current)
            continue
        if current is not None:
            current["text"] += ("\n" if current["text"] else "") + line

    trimmed = []
    for index, message in enumerate(messages[-limit:], start=max(0, len(messages) - limit)):
        trimmed.append({"id": index, "sender": message["sender"], "text": message["text"].strip()})
    return trimmed


def canonical_agent_name(agent: Any) -> str:
    normalized = str(agent or "").strip().lower().replace("-", "_").replace(" ", "_")
    return AGENT_ALIASES.get(normalized, normalized)


def canonical_agent_list(agents: Any) -> list[str]:
    if not isinstance(agents, list):
        return []
    normalized: list[str] = []
    for agent in agents:
        name = canonical_agent_name(agent)
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def canonical_agent_config(agent_config: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for agent, config in agent_config.items():
        normalized.setdefault(canonical_agent_name(agent), config)
    return normalized


def canonical_agent_statuses(agent_statuses: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for agent, status in agent_statuses.items():
        normalized[canonical_agent_name(agent)] = status
    return normalized


def build_token_usage(
    token_counts: dict[str, int],
    agent_config: dict[str, Any],
    main_agents: list[str],
) -> list[dict[str, Any]]:
    agent_config = canonical_agent_config(agent_config)
    canonical_counts: dict[str, int] = {}
    for agent_name, count in token_counts.items():
        canonical = canonical_agent_name(agent_name)
        canonical_counts[canonical] = canonical_counts.get(canonical, 0) + int(count or 0)
    ordered = canonical_agent_list(main_agents)
    for agent_name in canonical_counts:
        if agent_name not in ordered:
            ordered.append(agent_name)
    usage: list[dict[str, Any]] = []
    for agent_name in ordered:
        config = agent_config.get(agent_name) or {}
        used = int(canonical_counts.get(agent_name, 0))
        limit = int(config.get("token_limit", 0) or 0)
        warning = int(config.get("token_warning", 0) or 0)
        percent = round(used * 100.0 / limit, 1) if limit > 0 else None
        usage.append(
            {
                "agent": agent_name,
                "used": used,
                "limit": limit,
                "warning": warning,
                "percent": percent,
            }
        )
    return usage


def agent_status_value(record: Any) -> str:
    if isinstance(record, dict):
        return str(record.get("status", "available")).lower()
    if isinstance(record, str):
        return record.lower()
    return "available"


def agent_is_live(agent: str, agent_statuses: dict[str, Any]) -> bool:
    return agent_status_value(agent_statuses.get(canonical_agent_name(agent))) in {"available", "low"}


def normalize_fallback_candidates(candidates: Any) -> list[tuple[str, bool]]:
    if isinstance(candidates, dict):
        candidates = candidates.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    normalized: list[tuple[str, bool]] = []
    for item in candidates:
        if isinstance(item, str):
            normalized.append((canonical_agent_name(item), False))
            continue
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("agent") or "").strip()
            if name:
                normalized.append((canonical_agent_name(name), bool(item.get("can_fill_main_seat"))))
    return normalized


def agent_can_fill_lane(
    agent: str,
    *,
    agent_config: dict[str, Any],
    main_agents: list[str],
    direct_agents: list[str],
    fallback_candidate: bool = False,
    fallback_allows_fill: bool = False,
    active_candidate: bool = False,
) -> bool:
    config = agent_config.get(agent) or {}
    if agent in main_agents:
        return True
    if "can_fill_main_seat" in config:
        return bool(config.get("can_fill_main_seat"))
    if fallback_allows_fill:
        return True
    return active_candidate and fallback_candidate and agent in direct_agents


def append_lane_agent(selected: list[str], agent: str, agent_statuses: dict[str, Any]) -> bool:
    if not agent or agent in selected or not agent_is_live(agent, agent_statuses):
        return False
    selected.append(agent)
    return len(selected) >= LANE_AGENT_LIMIT


def build_lane_agents(
    main_agents: list[str],
    direct_agents: list[str],
    agent_config: dict[str, Any],
    agent_statuses: dict[str, Any],
    fallback_config: dict[str, Any] | None = None,
    active_agents: list[str] | None = None,
) -> list[str]:
    selected: list[str] = []
    main_agents = canonical_agent_list(main_agents)
    direct_agents = canonical_agent_list(direct_agents)
    agent_config = canonical_agent_config(agent_config)
    agent_statuses = canonical_agent_statuses(agent_statuses)
    fallback_config = fallback_config or {}
    active_agents = canonical_agent_list(active_agents or [])

    def consider(
        agent: str,
        *,
        fallback_candidate: bool = False,
        fallback_allows_fill: bool = False,
        active_candidate: bool = False,
    ) -> bool:
        agent = canonical_agent_name(agent)
        if agent in main_agents and agent not in selected and agent_is_live(agent, agent_statuses):
            return False
        if agent not in agent_config:
            return False
        if not agent_can_fill_lane(
            agent,
            agent_config=agent_config,
            main_agents=main_agents,
            direct_agents=direct_agents,
            fallback_candidate=fallback_candidate,
            fallback_allows_fill=fallback_allows_fill,
            active_candidate=active_candidate,
        ):
            return False
        return append_lane_agent(selected, agent, agent_statuses)

    for agent in main_agents:
        if append_lane_agent(selected, agent, agent_statuses):
            return selected
        if agent_is_live(agent, agent_statuses):
            continue

        filled_slot = False
        before_count = len(selected)
        for candidate in active_agents:
            if consider(candidate, fallback_candidate=True, active_candidate=True):
                return selected
            if len(selected) > before_count:
                filled_slot = True
                break
        if filled_slot:
            continue

        before_count = len(selected)
        for candidate in direct_agents:
            if consider(candidate, fallback_candidate=True):
                return selected
            if len(selected) > before_count:
                filled_slot = True
                break
        if filled_slot:
            continue

        fallback_candidates = normalize_fallback_candidates(
            fallback_config.get(agent, DEFAULT_AGENT_FALLBACKS.get(agent, []))
        )
        before_count = len(selected)
        for candidate, allows_fill in fallback_candidates:
            if consider(candidate, fallback_candidate=True, fallback_allows_fill=allows_fill):
                return selected
            if len(selected) > before_count:
                break

    for candidate in direct_agents:
        if consider(candidate, fallback_candidate=True):
            return selected

    return selected[:LANE_AGENT_LIMIT]


def proposal_snapshot(proposal: Any) -> dict[str, Any] | None:
    if not isinstance(proposal, dict):
        return None
    raw = str(proposal.get("raw") or "")
    return {
        "id": proposal.get("id"),
        "summary": proposal.get("summary"),
        "proposed_by": proposal.get("proposed_by"),
        "raw": raw[:REMOTE_PROPOSAL_RAW_LIMIT],
        "raw_truncated": len(raw) > REMOTE_PROPOSAL_RAW_LIMIT,
        "execution_estimate": proposal.get("execution_estimate"),
    }


def compact_summary(text: str, limit: int = TRACE_SUMMARY_LIMIT) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(">>>"):
            return stripped[:limit]
    return ""


def signal_from_line(line: str) -> tuple[str, str | None] | None:
    stripped = line.strip()
    if not stripped.startswith(">>>"):
        return None
    body = stripped[3:].strip()
    upper = body.upper()
    for signal in ("TASK_COMPLETE", "TASK COMPLETE", "HANDOFF", "QUESTION", "PROPOSAL", "BLOCKED", "SKIP"):
        if upper == signal or upper.startswith(f"{signal} ") or upper.startswith(f"{signal} >>"):
            normalized = "TASK_COMPLETE" if signal == "TASK COMPLETE" else signal
            target = None
            if normalized == "HANDOFF" and ">>" in body:
                target = body.rsplit(">>", 1)[1].strip() or None
            return normalized, target
    return None


def agent_trace_from_transcript(messages: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        sender = str(message.get("sender") or "unknown")
        text = str(message.get("text") or "")
        for line in text.splitlines():
            parsed = signal_from_line(line)
            if parsed is None:
                continue
            signal, target = parsed
            items.append(
                {
                    "message_id": message.get("id"),
                    "agent": sender,
                    "signal": signal,
                    "target": target,
                    "summary": compact_summary(text),
                }
            )
    return items[-limit:]


def packet_trace_from_file(packet_path: Path | None, limit: int = 8) -> list[dict[str, Any]]:
    if packet_path is None or not packet_path.exists():
        return []
    try:
        records = packet_records_from_jsonl(packet_path.read_text(encoding="utf-8-sig"), limit=limit)
    except OSError:
        return []
    items: list[dict[str, Any]] = []
    for record in records:
        packet = record.get("packet") if isinstance(record, dict) else {}
        packet = packet if isinstance(packet, dict) else {}
        context = record.get("context") if isinstance(record, dict) else {}
        context = context if isinstance(context, dict) else {}
        observed = packet.get("observed") if isinstance(packet.get("observed"), list) else []
        risks = packet.get("risks") if isinstance(packet.get("risks"), list) else []
        items.append(
            {
                "timestamp": record.get("timestamp"),
                "agent": packet.get("agent") or record.get("sender") or "unknown",
                "stance": packet.get("stance") or "UNKNOWN",
                "signal": packet.get("signal") or "UNKNOWN",
                "next_action": packet.get("next_action") or "",
                "observed_count": len(observed),
                "risk_count": len(risks),
                "round": record.get("round"),
                "stage": context.get("confirmation", {}).get("stage")
                if isinstance(context.get("confirmation"), dict)
                else None,
            }
        )
    return items


def trace_snapshot(messages: list[dict[str, Any]], packet_path: Path | None) -> dict[str, Any]:
    return {
        "agent": agent_trace_from_transcript(messages),
        "packets": packet_trace_from_file(packet_path),
    }


def parse_query_int(
    query: dict[str, list[str]],
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw or default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Query parameter '{name}' must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"Query parameter '{name}' must be at least {minimum}.")
    if maximum is not None and value > maximum:
        return maximum
    return value


def git_environment(proj_path: Path | None) -> dict[str, Any] | None:
    if proj_path is None:
        return None
    root = Path(proj_path)
    if not (root / ".git").exists():
        return None

    def run_git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout.strip()

    try:
        branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
        status_lines = [line for line in run_git("status", "--porcelain").splitlines() if line.strip()]
        staged = sum(1 for line in status_lines if line[:1] not in {" ", "?"})
        unstaged = sum(1 for line in status_lines if len(line) > 1 and line[1] != " ")
        commit_hash, _, commit_age = run_git("log", "-1", "--format=%h|%cr").partition("|")
        return {
            "branch": branch,
            "staged": staged,
            "unstaged": unstaged,
            "clean": not status_lines,
            "last_commit": commit_hash,
            "last_commit_age": commit_age,
        }
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None


def codegraph_stats(proj_path: Path | None) -> dict[str, Any] | None:
    if proj_path is None:
        return None
    root = Path(proj_path)
    candidates = [
        root / "codegraph.db",
        root / ".codegraph" / "codegraph.db",
        root / ".codegraph" / "index.db",
    ]
    db_path = next((candidate for candidate in candidates if candidate.exists()), None)
    if db_path is None:
        return None
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return None
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"nodes", "edges", "files"} <= tables:
            return None
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("files", "nodes", "edges")
        }
        return {
            "healthy": True,
            "files": counts["files"],
            "nodes": counts["nodes"],
            "edges": counts["edges"],
            "last_indexed": time.strftime("%H:%M:%S", time.localtime(db_path.stat().st_mtime)),
        }
    except (sqlite3.Error, OSError):
        return None
    finally:
        connection.close()


def system_memory_percent() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found]

        return float(psutil.virtual_memory().percent)
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return float(status.dwMemoryLoad)
    return None


def detect_tailnet_ip() -> str | None:
    try:
        entries = socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET)
    except OSError:
        return None
    for entry in entries:
        address = entry[4][0]
        if is_tailnet_ipv4_host(address):
            return address
    return None


def monitor_stats() -> dict[str, Any]:
    stats: dict[str, Any] = {"pid": os.getpid()}
    memory = system_memory_percent()
    if memory is not None:
        stats["ram_percent"] = memory
    try:
        import psutil  # type: ignore[import-not-found]

        stats["cpu_percent"] = float(psutil.cpu_percent(interval=None))
    except ImportError:
        pass
    tailnet_ip = detect_tailnet_ip()
    if tailnet_ip:
        stats["tailnet_ip"] = tailnet_ip
    return stats


class RemoteEventBuffer:
    def __init__(self, max_events: int = 256) -> None:
        self.max_events = max_events
        self._events: list[dict[str, Any]] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def append(self, kind: str, sender: str, text: str) -> None:
        event_text = text if kind == "message_delta" else text.strip()
        payload = {
            "id": self._next_id,
            "kind": kind,
            "sender": sender,
            "text": event_text,
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

    def authorize_admin(self, token: str) -> bool:
        return bool(token) and secrets.compare_digest(token, self.admin_token)

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

    def agent_activity_start(self, agent_name: str, mode: str) -> None:
        self.events.append("activity", agent_name.lower(), f"started {mode}")

    def agent_activity_finish(self, agent_name: str, mode: str, elapsed_seconds: float) -> None:
        self.events.append("activity", agent_name.lower(), f"finished {mode} in {elapsed_seconds:.1f}s")

    def agent_output_start(self, agent_name: str, mode: str) -> None:
        self.events.append("message_stream_start", agent_name.lower(), mode)

    def agent_output_delta(self, agent_name: str, text: str) -> None:
        if text:
            self.events.append("message_delta", agent_name.lower(), text)

    def agent_output_finish(self, agent_name: str) -> None:
        self.events.append("message_stream_finish", agent_name.lower(), "")

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
        self._workbench_cache: tuple[float, dict[str, Any]] | None = None
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
            self._workbench_cache = None
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
            session_budget = self.app.session_token_budget()
            token_line = self.app.stream.build_token_usage_line(token_counts, session_budget)
            app_config = getattr(self.app, "config", None)
            agent_config = canonical_agent_config(
                (app_config.get("agents") if isinstance(app_config, dict) else None) or {}
            )
            fallback_config = (app_config.get("agent_fallbacks") if isinstance(app_config, dict) else None) or {}
            proj_config = getattr(self.app, "proj_config", None) or {}
            main_agents = canonical_agent_list(list(proj_config.get("agents") or []))
            direct_agents = sorted(canonical_agent_list(list(proj_config.get("direct_agents") or [])))
            try:
                agent_statuses = canonical_agent_statuses(self.app.load_agent_statuses())
            except (AttributeError, OSError, ValueError, TypeError):
                agent_statuses = {}
            active_agents = []
            if self.command_running() or self.app.state.get("status") not in {"idle", "blocked", "awaiting_approval"}:
                active_agents = canonical_agent_list([
                    str(agent)
                    for agent in [
                        self.app.state.get("next_agent"),
                        self.app.state.get("last_agent"),
                        *list(self.app.state.get("expected_agents") or []),
                    ]
                    if agent
                ])
            lane_agents = build_lane_agents(
                main_agents,
                direct_agents,
                agent_config,
                agent_statuses,
                fallback_config,
                active_agents,
            )
            transcript = parse_chatboks_messages(self.app.chatboks_md, limit=transcript_limit)
            packet_path = getattr(self.app, "packet_file", None)
            return {
                "project": self.app.project,
                "projects": self.available_projects(),
                "session": self.app.state.get("session"),
                "status": self.app.state.get("status"),
                "active_task": self.app.state.get("active_task"),
                "next_agent": self.app.state.get("next_agent"),
                "last_agent": self.app.state.get("last_agent"),
                "round": self.app.state.get("round"),
                "expected_agents": list(self.app.state.get("expected_agents") or []),
                "completed_agents": list(self.app.state.get("completed_agents") or []),
                "collaboration_mode": self.app.state.get("collaboration_mode"),
                "context_mode": self.app.state.get("context_mode"),
                "proposal": proposal_snapshot(self.app.state.get("proposal")),
                "command_running": self.command_running(),
                "command_text": self._command_text,
                "agents": main_agents,
                "direct_agents": direct_agents,
                "agent_statuses": agent_statuses,
                "lane_agents": lane_agents,
                "token_line": token_line,
                "token_usage": build_token_usage(token_counts, agent_config, main_agents),
                "session_budget": session_budget if isinstance(session_budget, dict) else None,
                "transcript": transcript,
                "trace": trace_snapshot(transcript, packet_path if isinstance(packet_path, Path) else None),
                "events": self.events.since(cursor),
            }

    def workbench_status(self) -> dict[str, Any]:
        now = time.time()
        cached = getattr(self, "_workbench_cache", None)
        if cached is not None and now - cached[0] < WORKBENCH_STATUS_CACHE_SECONDS:
            return cached[1]
        proj_path = getattr(self.app, "proj_path", None)
        payload = {
            "project": getattr(self.app, "project", self.project),
            "generated_at": time.strftime("%H:%M:%S"),
            "environment": git_environment(proj_path),
            "graph": codegraph_stats(proj_path),
            "monitor": monitor_stats(),
        }
        self._workbench_cache = (now, payload)
        return payload


class RemoteBridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        session: RemoteSession,
        auth: RemoteAuth,
        operator_status_path: Path | None = None,
    ) -> None:
        super().__init__(address, handler)
        self.session = session
        self.auth = auth
        self.operator_status_path = operator_status_path

    def operator_status_payload(self, *, include_admin_token: bool = True) -> dict[str, Any]:
        pair_code, pair_ttl = self.auth.current_pair_code()
        expires_at = int(time.time() + pair_ttl)
        app = getattr(self.session, "app", None)
        project = getattr(app, "project", getattr(self.session, "project", "unknown"))
        payload = {
            "status": "running",
            "project": project,
            "host": self.server_address[0],
            "port": self.server_address[1],
            "base_url": f"http://{self.server_address[0]}:{self.server_address[1]}",
            "pair_code": pair_code,
            "pair_code_ttl_seconds": pair_ttl,
            "pair_code_expires_at": expires_at,
            "session_token_ttl_seconds": SESSION_TOKEN_TTL_SECONDS,
            "pid": os.getpid(),
            "updated_at": int(time.time()),
        }
        if include_admin_token:
            payload["admin_token"] = self.auth.admin_token
        return payload

    def write_operator_status(self) -> None:
        if self.operator_status_path is None:
            return
        payload = self.operator_status_payload()
        self.operator_status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.operator_status_path.with_suffix(self.operator_status_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self.operator_status_path)

    def rotate_pair_code_for_operator(self) -> tuple[str, int]:
        pair_code, pair_ttl = self.auth.rotate_pair_code()
        self.write_operator_status()
        return pair_code, pair_ttl


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
        if parsed.path in WORKBENCH_STATIC_ROUTES:
            relative_path, content_type = WORKBENCH_STATIC_ROUTES[parsed.path]
            self.respond_static(relative_path, content_type)
            return
        if parsed.path == "/api/admin/status":
            if not self.origin_allowed():
                return
            if not self.admin_authorized():
                return
            self.server.write_operator_status()
            self.respond_json(self.server.operator_status_payload(include_admin_token=False))
            return
        if parsed.path == "/api/workbench":
            if not self.origin_allowed():
                return
            if not self.authorized():
                return
            self.respond_json(self.server.session.workbench_status())
            return
        if parsed.path == "/api/session":
            if not self.origin_allowed():
                return
            if not self.authorized():
                return
            query = urllib.parse.parse_qs(parsed.query)
            try:
                cursor = parse_query_int(query, "cursor", 0)
                limit = parse_query_int(query, "limit", TRANSCRIPT_LIMIT, maximum=MAX_TRANSCRIPT_LIMIT)
            except ValueError as exc:
                self.respond_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
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
        if parsed.path == "/api/admin/pair-code":
            if not self.origin_allowed():
                return
            if not self.admin_authorized():
                return
            pair_code, ttl = self.server.rotate_pair_code_for_operator()
            self.respond_json(
                {
                    "pair_code": pair_code,
                    "ttl_seconds": ttl,
                    "expires_at": int(time.time() + ttl),
                }
            )
            return
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
            self.server.write_operator_status()
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

    def admin_authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.write_cors_headers(self.request_origin())
            self.send_header("WWW-Authenticate", 'Bearer realm="ChatBoks Remote Admin"')
            self.end_headers()
            return False
        provided = header.removeprefix("Bearer ").strip()
        if not self.server.auth.authorize_admin(provided):
            self.respond_error(HTTPStatus.FORBIDDEN, "Invalid admin token")
            return False
        return True

    def read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0:
            raise ValueError("Invalid Content-Length")
        if length > MAX_JSON_BODY_BYTES:
            raise ValueError(f"Request body exceeds {MAX_JSON_BODY_BYTES} bytes.")
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        except UnicodeDecodeError as exc:
            raise ValueError("Request body must be UTF-8 JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

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

    def respond_static(self, relative_path: str, content_type: str) -> None:
        file_path = WORKBENCH_WWW_ROOT / relative_path
        try:
            body = file_path.read_bytes()
        except OSError:
            self.respond_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        self.send_response(HTTPStatus.OK)
        self.write_security_headers(include_csp=content_type.startswith("text/html"))
        self.send_header("Content-Type", content_type)
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


def default_operator_status_path() -> Path:
    return Path.cwd() / ".chatboks" / OPERATOR_STATUS_FILENAME


def read_operator_status_payload(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"could not read operator file: {exc}"
    if not isinstance(payload, dict):
        return None, "operator file is not a JSON object"
    return payload, None


def probe_operator_bridge(
    payload: dict[str, Any],
    *,
    timeout: float = OPERATOR_PROBE_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    base_url = str(payload.get("base_url") or "").rstrip("/")
    admin_token = str(payload.get("admin_token") or "")
    if not base_url or not admin_token:
        return False, "operator file is missing base_url/admin_token"

    def request_json(path: str) -> dict[str, Any] | None:
        request = urllib.request.Request(
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {admin_token}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        try:
            decoded = json.loads(body or "{}")
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    try:
        status = request_json("/api/admin/status")
        if status is not None:
            pid = status.get("pid")
            return True, f"active bridge answered at {base_url} (pid {pid})"
        return True, f"active bridge answered at {base_url}"
    except urllib.error.HTTPError as exc:
        if exc.code == HTTPStatus.NOT_FOUND:
            try:
                request_json("/api/workbench")
                return True, f"active legacy bridge answered at {base_url}"
            except urllib.error.HTTPError as fallback_exc:
                if fallback_exc.code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
                    return False, f"bridge at {base_url} rejected the operator credentials"
                return False, f"bridge at {base_url} returned HTTP {fallback_exc.code}"
            except OSError as fallback_exc:
                return False, f"no bridge answered at {base_url}: {fallback_exc}"
        if exc.code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            return False, f"bridge at {base_url} rejected the operator credentials"
        return False, f"bridge at {base_url} returned HTTP {exc.code}"
    except OSError as exc:
        return False, f"no bridge answered at {base_url}: {exc}"


def ensure_operator_file_available(path: Path) -> None:
    payload, error = read_operator_status_payload(path)
    if error == "missing":
        return
    if payload is None:
        print(f"Ignoring stale remote bridge operator file: {error}")
        return
    active, detail = probe_operator_bridge(payload)
    if not active:
        print(f"Ignoring stale remote bridge operator file: {detail}")
        return
    raise RuntimeError(
        f"An active ChatBoks remote bridge already owns {path}: {detail}. "
        "Stop that bridge first, or pass a different --operator-file."
    )


def rotate_pair_code_from_operator_file(path: Path) -> int:
    payload, error = read_operator_status_payload(path)
    if error == "missing":
        print(f"No remote bridge operator file found: {path}")
        print("Start the bridge first, or pass --operator-file with the active bridge file.")
        return 2
    if payload is None:
        print(f"Could not read remote bridge operator file: {error}")
        return 2
    active, detail = probe_operator_bridge(payload)
    if not active:
        print(f"Stale remote bridge operator file: {detail}")
        print("Start the bridge again, or delete the stale operator file.")
        return 1
    base_url = str(payload.get("base_url") or "").rstrip("/")
    admin_token = str(payload.get("admin_token") or "")
    if not base_url or not admin_token:
        print(f"Operator file is missing base_url/admin_token: {path}")
        return 2
    request = urllib.request.Request(
        f"{base_url}/api/admin/pair-code",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"Bridge rejected pair-code rotation: HTTP {exc.code}")
        return 1
    except OSError as exc:
        print(f"Could not reach running bridge at {base_url}: {exc}")
        return 1
    pair_code = result.get("pair_code")
    ttl = result.get("ttl_seconds")
    print(f"Pairing code: {pair_code} (expires in {ttl} seconds)")
    print(f"Bridge URL: {base_url}")
    return 0


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Secure remote bridge for ChatBoks")
    parser.add_argument("project", nargs="?", help="Project name from config.yaml")
    parser.add_argument("--config", type=Path, default=None, help="Optional path to ChatBoks config.yaml")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Loopback port for the bridge (default: 8765)")
    parser.add_argument("--token", help="Admin bearer token for API access. Random if omitted.")
    parser.add_argument("--show-admin-token", action="store_true", help="Print the admin token on startup.")
    parser.add_argument(
        "--operator-file",
        type=Path,
        default=None,
        help=f"Runtime operator file path (default: .chatboks/{OPERATOR_STATUS_FILENAME})",
    )
    parser.add_argument(
        "--rotate-pair-code",
        action="store_true",
        help="Ask the running bridge for a new pairing code using the local operator file.",
    )
    parser.add_argument(
        "--allow-tailnet-bind",
        action="store_true",
        help="Allow binding to a Tailscale 100.64.0.0/10 IPv4 address when Tailscale Serve is unavailable.",
    )
    args = parser.parse_args()
    operator_status_path = (args.operator_file or default_operator_status_path()).expanduser().resolve()

    if args.rotate_pair_code:
        return rotate_pair_code_from_operator_file(operator_status_path)

    if not args.project:
        parser.error("project is required unless --rotate-pair-code is used")

    if not is_allowed_bind_host(args.host, allow_tailnet_bind=args.allow_tailnet_bind):
        raise SystemExit(
            "Refusing unsafe bind. Use loopback, or pass --allow-tailnet-bind with a Tailscale 100.64.0.0/10 IPv4 address."
        )
    try:
        ensure_operator_file_available(operator_status_path)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    session = RemoteSession(args.project, config_path=args.config)
    admin_token = args.token or secrets.token_urlsafe(24)
    auth = RemoteAuth(admin_token)
    server = RemoteBridgeServer((args.host, args.port), RemoteHandler, session, auth, operator_status_path)
    server.write_operator_status()
    pair_code, pair_ttl = auth.current_pair_code()

    print(f"ChatBoks remote bridge for project '{args.project}'")
    print(f"Listening on http://{args.host}:{args.port}/")
    print(f"Workbench UI: http://{args.host}:{args.port}/workbench")
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
    print(f"Operator file: {operator_status_path}")
    print("New code command: python remote_control.py --rotate-pair-code")
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
