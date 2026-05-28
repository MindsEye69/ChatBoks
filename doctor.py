#!/usr/bin/env python3
"""Chatboks doctor: lightweight local diagnostics."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - diagnostic path
    yaml = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Chatboks install")
    parser.add_argument("project", nargs="?", help="Optional project name from config.yaml")
    parser.add_argument("--config", type=Path, default=Path("~/.chatboks/config.yaml").expanduser())
    args = parser.parse_args()

    ok = True
    print("Chatboks doctor")
    print("================")

    if yaml is None:
        print("FAIL pyyaml is not installed")
        return 1

    if not args.config.exists():
        print(f"FAIL missing config: {args.config}")
        return 1

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    print(f"OK   config: {args.config}")

    projects = config.get("projects", {})
    selected = [args.project] if args.project else sorted(projects)
    for project in selected:
        if project not in projects:
            print(f"FAIL unknown project: {project}")
            ok = False
            continue
        ok = check_project(project, projects[project], config) and ok

    return 0 if ok else 1


def check_project(project: str, project_config: dict, config: dict) -> bool:
    ok = True
    project_path = Path(project_config["path"]).expanduser()
    print(f"\n[{project}]")
    if project_path.exists():
        print(f"OK   project path: {project_path}")
    else:
        print(f"FAIL project path missing: {project_path}")
        return False

    for agent_name in project_config.get("agents", []):
        agent_config = config.get("agents", {}).get(agent_name, {})
        cli = agent_config.get("cli", agent_name)
        role_file = agent_config.get("role_file")
        cli_ok = Path(cli).exists() or shutil.which(cli) is not None
        print(("OK  " if cli_ok else "WARN") + f" {agent_name} cli: {cli}")
        if role_file:
            role_path = project_path / role_file
            role_ok = role_path.exists()
            print(("OK  " if role_ok else "WARN") + f" {agent_name} role file: {role_path}")
        ok = ok and cli_ok

    db_path = find_codegraph_db(project_path, config)
    if db_path:
        try:
            with sqlite3.connect(db_path) as conn:
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            print(f"OK   codegraph sqlite: {db_path} ({len(tables)} tables)")
        except sqlite3.Error as exc:
            print(f"FAIL codegraph sqlite unreadable: {db_path} ({exc})")
            ok = False
    else:
        print("WARN codegraph sqlite not found")

    state_path = project_path / ".chatboks" / "state.json"
    print(("OK  " if state_path.exists() else "WARN") + f" state file: {state_path}")
    return ok


def find_codegraph_db(project_path: Path, config: dict) -> Path | None:
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


if __name__ == "__main__":
    raise SystemExit(main())
