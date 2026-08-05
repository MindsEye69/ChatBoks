"""Native desktop launcher for the ChatBoks Workbench."""

from __future__ import annotations

import argparse
import io
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import yaml

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChatBoks desktop Workbench")
    parser.add_argument("project", nargs="?", help="Project name from config.yaml")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="ChatBoks configuration file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_gui_stdio()
        bridge = DesktopBridge(args.project or default_project_name(args.config), args.config)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
