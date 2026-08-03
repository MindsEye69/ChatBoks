"""ChatBoks application version derived from the shared Git history."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


DEVELOPMENT_MAJOR = 0
DEVELOPMENT_MINOR = 1
VERSION_ANCHOR_COMMIT = "61650e87158800ba6c698ec16e2aa90daa24792b"
VERSION_ANCHOR_GRACE_COMMITS = 1
VERSION_STAMP_FILENAME = "chatboks-version.txt"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d{2}$")


def format_development_version(build_number: int) -> str:
    """Format a development build without ever promoting it to release 1.0."""
    if build_number < 0:
        raise ValueError("build_number must be non-negative")
    minor = DEVELOPMENT_MINOR + build_number // 100
    build = build_number % 100
    return f"{DEVELOPMENT_MAJOR}.{minor}.{build:02d}"


def version_for_commit_distance(commit_distance: int) -> str:
    build_number = max(0, commit_distance - VERSION_ANCHOR_GRACE_COMMITS)
    return format_development_version(build_number)


def _valid_version(value: str) -> str | None:
    value = value.strip()
    return value if VERSION_PATTERN.fullmatch(value) else None


def _version_override() -> str | None:
    environment_version = _valid_version(os.environ.get("CHATBOKS_VERSION", ""))
    if environment_version:
        return environment_version
    runtime_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    stamp_path = runtime_root / VERSION_STAMP_FILENAME
    try:
        return _valid_version(stamp_path.read_text(encoding="ascii"))
    except OSError:
        return None


def _git_commit_distance() -> int | None:
    repo_root = Path(__file__).resolve().parent
    run_options: dict[str, object] = {}
    if os.name == "nt":
        run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{VERSION_ANCHOR_COMMIT}..HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
            **run_options,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def resolve_version() -> str:
    override = _version_override()
    if override:
        return override
    commit_distance = _git_commit_distance()
    return version_for_commit_distance(commit_distance or 0)


__version__ = resolve_version()
CHATBOKS_VERSION_LABEL = f"v{__version__}"
