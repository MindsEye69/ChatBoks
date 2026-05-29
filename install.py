#!/usr/bin/env python3
"""ChatBoks first-run setup helper.

The installer is intentionally conservative: it checks local prerequisites,
asks before installing anything, and leaves ChatBoks usable with degraded
context if CodeGraph is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - bootstrap path
    yaml = None


CODEGRAPH_PACKAGE = "@colbymchenry/codegraph"
NODE_PACKAGE = "OpenJS.NodeJS.LTS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up ChatBoks dependencies")
    parser.add_argument("project", nargs="?", help="Optional project name from config.yaml")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--yes", action="store_true", help="Assume yes for install prompts")
    args = parser.parse_args()

    if yaml is None:
        print("FAIL pyyaml is not installed. Run: pip install -r requirements.txt")
        return 1
    if not args.config.exists():
        print(f"FAIL missing config: {args.config}")
        return 1

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    projects = config.get("projects", {})
    selected = [args.project] if args.project else sorted(projects)

    ok = True
    if not ensure_node(args.yes):
        ok = False
    if not ensure_codegraph(args.yes):
        ok = False

    for project in selected:
        if project not in projects:
            print(f"WARN unknown project skipped: {project}")
            ok = False
            continue
        ok = ensure_project_codegraph(project, projects[project], config) and ok

    return 0 if ok else 1


def ensure_node(assume_yes: bool) -> bool:
    if shutil.which("node") and (shutil.which("npm") or shutil.which("npm.cmd")):
        print("OK   Node/npm available")
        return True

    print("WARN Node.js/npm not found. CodeGraph setup will be degraded.")
    if os.name == "nt" and ask("Install Node.js LTS via winget now?", assume_yes):
        return run(["winget", "install", NODE_PACKAGE, "--silent", "--accept-package-agreements", "--accept-source-agreements"])
    return False


def ensure_codegraph(assume_yes: bool) -> bool:
    if find_codegraph_command():
        print("OK   codegraph command available")
        return True

    if npm_package_installed(CODEGRAPH_PACKAGE):
        print("WARN CodeGraph package appears installed, but codegraph command is not on PATH")
        return False

    print("WARN CodeGraph is not installed. ChatBoks context will be degraded.")
    if ask("Install CodeGraph globally with npm now?", assume_yes):
        npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
        return run([npm, "install", "-g", CODEGRAPH_PACKAGE])
    return False


def ensure_project_codegraph(project: str, project_config: dict[str, Any], config: dict[str, Any]) -> bool:
    project_path = Path(project_config["path"]).expanduser()
    if not project_path.exists():
        print(f"WARN {project}: project path missing: {project_path}")
        return False
    if find_codegraph_db(project_path, config):
        print(f"OK   {project}: CodeGraph database present")
        return True

    codegraph = find_codegraph_command()
    if not codegraph:
        print(f"WARN {project}: CodeGraph database missing and codegraph command unavailable")
        return False

    print(f"INFO {project}: initializing CodeGraph at {project_path}")
    return run([str(codegraph), "init", "-i"], cwd=project_path)


def find_codegraph_command() -> Path | None:
    found = shutil.which("codegraph") or shutil.which("codegraph.cmd")
    if found:
        return Path(found)
    npm_root = Path(os.environ.get("APPDATA", "")) / "npm"
    for candidate in (npm_root / "codegraph.cmd", npm_root / "codegraph"):
        if candidate.exists():
            return candidate
    return None


def npm_package_installed(package: str) -> bool:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        return False
    result = subprocess.run(
        [npm, "list", "-g", package, "--depth=0", "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return package in (data.get("dependencies") or {})


def find_codegraph_db(project_path: Path, config: dict[str, Any]) -> Path | None:
    candidates = (
        config.get("context", {})
        .get("codegraph", {})
        .get("db_candidates", ["codegraph.db", ".codegraph/codegraph.db", ".codegraph/index.db"])
    )
    for candidate in candidates:
        path = project_path / candidate
        if path.exists():
            return path
    return None


def ask(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"YES  {question}")
        return True
    answer = input(f"{question} [Y/n] ").strip().lower()
    return answer in {"", "y", "yes"}


def run(command: list[str], cwd: Path | None = None) -> bool:
    try:
        result = subprocess.run(command, cwd=cwd, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL {' '.join(command)} ({exc})")
        return False
    if result.returncode != 0:
        print(f"FAIL {' '.join(command)} exited {result.returncode}")
        return False
    return True


def default_config_path() -> Path:
    local = Path(__file__).resolve().parent / "config.yaml"
    if local.exists():
        return local
    return Path("~/.chatboks/config.yaml").expanduser()


if __name__ == "__main__":
    raise SystemExit(main())
