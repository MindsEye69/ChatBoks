"""Native desktop launcher for the ChatBoks Workbench."""

from __future__ import annotations

import argparse
import io
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import yaml

from integration_worker_protocol import INTEGRATION_WORKER_FLAG
from remote_control import RemoteAuth, RemoteBridgeServer, RemoteHandler, RemoteSession


def ensure_gui_stdio() -> None:
    """Give console-oriented dependencies harmless streams in a --noconsole build."""
    for stream_name in ("stdin", "stdout", "stderr"):
        if getattr(sys, stream_name, None) is None:
            setattr(sys, stream_name, io.StringIO())


def default_config_path() -> Path:
    """Find the editable project config when the launcher runs from dist/."""
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        for root in (executable_dir.parent, executable_dir):
            candidate = root / "config.yaml"
            if candidate.exists():
                return candidate
    return Path(__file__).resolve().parent / "config.yaml"


def default_project_name(config_path: Path) -> str:
    """Pick a stable initial project when the old `chatboks` entry was renamed."""
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "chatboks"
    projects = config.get("projects") or {}
    if "chatboks" in projects:
        return "chatboks"
    for name in projects:
        if str(name).casefold().startswith("chatboks"):
            return str(name)
    return str(next(iter(projects), "chatboks"))


def show_startup_error(error: Exception) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"ChatBoks could not start.\n\n{error}",
            "ChatBoks",
            0x10,
        )


def embedded_workbench_url(bridge_url: str, session_token: str) -> str:
    """Build a loopback-only URL whose bearer token is never sent in an HTTP request."""
    parsed = urllib.parse.urlparse(str(bridge_url or "").strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Embedded ChatBoks requires a loopback HTTP bridge.")
    if not session_token or len(session_token) > 256:
        raise ValueError("Embedded ChatBoks requires a valid session token.")
    fragment = urllib.parse.urlencode({"sessionToken": session_token}, quote_via=urllib.parse.quote)
    return f"{bridge_url.rstrip('/')}/workbench?embedded=1#{fragment}"


def write_embedded_bootstrap(path: Path, bridge_url: str, session_token: str) -> None:
    """Publish the one-time Lumen bootstrap atomically inside the user's profile."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "url": embedded_workbench_url(bridge_url, session_token),
        "pid": os.getpid(),
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(target)


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_for_embed_stop(
    stop_path: Path,
    parent_pid: int | None,
    *,
    poll_seconds: float = 0.2,
) -> str:
    """Keep the background bridge alive until Lumen stops it or exits."""
    while True:
        if stop_path.exists():
            return "stop"
        if parent_pid is not None and not process_is_running(parent_pid):
            return "parent-exited"
        time.sleep(poll_seconds)


class DesktopBridge:
    """Own a loopback bridge and expose only a short-lived client session to the webview."""

    def __init__(self, project: str, config_path: Path | None = None) -> None:
        self.session = RemoteSession(project, config_path=config_path, command_source="desktop")
        self.auth = RemoteAuth(secrets.token_urlsafe(24))
        self.server = RemoteBridgeServer(
            ("127.0.0.1", 0),
            RemoteHandler,
            self.session,
            self.auth,
            operator_status_path=None,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        pair_code, _ttl = self.auth.current_pair_code()
        paired = self.auth.exchange_pair_code(pair_code)
        if paired is None:  # pragma: no cover - defensive invariant
            self.close()
            raise RuntimeError("Could not create the desktop Workbench session.")
        self.session_token, _token_ttl = paired
        host, port = self.server.server_address[:2]
        self.bridge_url = f"http://{host}:{port}"

    def bootstrap(self) -> dict[str, str]:
        return {"bridgeUrl": self.bridge_url, "sessionToken": self.session_token}

    def choose_project_folder(self) -> str | None:
        """Open the native folder picker for the desktop-only project registry flow."""
        import webview

        if not webview.windows:
            return None
        selected = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return str(selected[0]) if selected else None

    def open_preview(self, target: str) -> dict[str, str]:
        """Open a user-selected local preview URL or project artifact in the default app."""
        value = str(target or "").strip()
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme in {"http", "https"}:
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Only local preview URLs can be opened from ChatBoks.")
            webbrowser.open(value)
            return {"status": "opened", "kind": "url"}

        project_root = Path(self.session.app.proj_path).resolve()
        artifact = Path(value).expanduser().resolve()
        if artifact.suffix.lower() not in {".html", ".htm", ".exe"}:
            raise ValueError("Preview supports local HTML files and Windows executables.")
        if not artifact.is_file() or not artifact.is_relative_to(project_root):
            raise ValueError("Preview files must exist inside the selected project.")
        if artifact.suffix.lower() == ".exe":
            extra: dict[str, Any] = {}
            if sys.platform == "win32":
                extra["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen([str(artifact)], cwd=str(artifact.parent), **extra)
            return {"status": "opened", "kind": "exe"}
        webbrowser.open(artifact.as_uri())
        return {"status": "opened", "kind": "html"}

    def close(self) -> None:
        self.session.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChatBoks desktop Workbench")
    parser.add_argument("project", nargs="?", help="Project name from config.yaml")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="ChatBoks configuration file")
    parser.add_argument("--embed-bootstrap", type=Path, help="One-time bootstrap file for a Lumen plugin host")
    parser.add_argument("--embed-stop", type=Path, help="Stop signal file for a Lumen plugin host")
    parser.add_argument("--parent-pid", type=int, help="Owning Lumen process id")
    return parser.parse_args(argv)


def _maybe_run_integration_worker(argv: list[str]) -> int | None:
    if not argv or argv[0] != INTEGRATION_WORKER_FLAG:
        return None
    ensure_gui_stdio()
    from integration_execution_runner import main as run_integration_worker

    return run_integration_worker(argv[1:])


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    worker_result = _maybe_run_integration_worker(raw_args)
    if worker_result is not None:
        return worker_result

    args = parse_args(raw_args)
    try:
        ensure_gui_stdio()
        bridge = DesktopBridge(args.project or default_project_name(args.config), args.config)
        if args.embed_bootstrap or args.embed_stop:
            if not args.embed_bootstrap or not args.embed_stop:
                raise ValueError("Lumen embed mode requires both bootstrap and stop paths.")
            args.embed_bootstrap.unlink(missing_ok=True)
            args.embed_stop.unlink(missing_ok=True)
            write_embedded_bootstrap(
                args.embed_bootstrap,
                bridge.bridge_url,
                bridge.session_token,
            )
            wait_for_embed_stop(args.embed_stop, args.parent_pid)
        else:
            import webview

            webview.create_window(
                "ChatBoks",
                f"{bridge.bridge_url}/workbench?desktop=1",
                js_api=bridge,
                width=1440,
                height=960,
                min_size=(1100, 720),
            )
            webview.start()
    except Exception as exc:  # noqa: BLE001 - native entry point must surface startup failures.
        show_startup_error(exc)
        return 1
    finally:
        if "bridge" in locals():
            bridge.close()
        if args.embed_bootstrap:
            args.embed_bootstrap.unlink(missing_ok=True)
        if args.embed_stop:
            args.embed_stop.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
