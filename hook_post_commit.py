#!/usr/bin/env python3
"""Git post-commit hook runner for ChatBoks async handoffs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - hook install should catch this
    yaml = None

from encoding_utils import configure_utf8_stdio, utf8_env


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run ChatBoks post-commit handoff hook")
    parser.add_argument("project")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--chatboks-root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    if yaml is None:
        return 0
    if not args.config.exists():
        return 0

    config = yaml.safe_load(args.config.read_text(encoding="utf-8-sig")) or {}
    project_config = (config.get("projects") or {}).get(args.project)
    if not project_config:
        return 0

    project_path = Path(project_config["path"]).expanduser().resolve()
    state_path = project_path / ".chatboks" / "state.json"
    chatboks_md = project_path / "chatboks.md"
    if not state_path.exists():
        return 0

    state = load_state(state_path)
    append_commit_message(chatboks_md, project_path)
    if state.get("status") != "handoff":
        return 0

    orchestrator = args.chatboks_root / "orchestrator.py"
    if not orchestrator.exists():
        return 0
    subprocess.run(
        [
            sys.executable,
            str(orchestrator),
            args.project,
            "--trigger=commit",
            "--config",
            str(args.config),
        ],
        cwd=project_path,
        env=utf8_env(),
        check=False,
    )
    return 0


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def append_commit_message(chatboks_md: Path, project_path: Path) -> None:
    commit_msg = git_output(project_path, ["git", "log", "-1", "--pretty=%B"]).strip()
    commit_hash = git_output(project_path, ["git", "log", "-1", "--pretty=%h"]).strip()
    author = git_output(project_path, ["git", "log", "-1", "--pretty=%an"]).strip()
    if not commit_hash:
        return
    chatboks_md.parent.mkdir(parents=True, exist_ok=True)
    with chatboks_md.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[SYSTEM] Commit by {author}: {commit_msg} ({commit_hash})\n")


def git_output(project_path: Path, command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_env(),
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


if __name__ == "__main__":
    raise SystemExit(main())
