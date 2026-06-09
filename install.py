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
import sys
import urllib.error
import urllib.request
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
    parser.add_argument("--agent-zero", action="store_true", help="Install/check Forge and offer to add Agent Zero to selected projects")
    parser.add_argument("--install-hook", action="store_true", help="Install ChatBoks post-commit handoff hook")
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
    if args.agent_zero and not ensure_agent_zero_ollama(config, args.yes):
        ok = False

    changed_config = False
    for project in selected:
        if project not in projects:
            print(f"WARN unknown project skipped: {project}")
            ok = False
            continue
        ok = ensure_project_codegraph(project, projects[project], config) and ok
        if args.install_hook:
            ok = ensure_project_hook(project, projects[project], args.config, args.yes) and ok
        if args.agent_zero:
            changed_config = offer_agent_zero(project, projects[project], args.yes) or changed_config

    if changed_config:
        args.config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        print(f"OK   updated config: {args.config}")

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


def ensure_agent_zero_ollama(config: dict[str, Any], assume_yes: bool) -> bool:
    agent_config = config.get("agents", {}).get("agent_zero", {})
    model = str(agent_config.get("model", "gemma3:4b"))
    endpoint = str(agent_config.get("endpoint", "http://127.0.0.1:11434/api/chat"))
    tags_endpoint = endpoint.replace("/api/chat", "/api/tags").replace("/api/generate", "/api/tags")

    models = fetch_ollama_models(tags_endpoint)
    if models is not None and model in models:
        print(f"OK   Agent Zero Ollama endpoint: {tags_endpoint}")
        print(f"OK   Agent Zero model available: {model}")
        return True

    ollama = shutil.which("ollama")
    print(("OK  " if ollama else "WARN") + f" ollama command: {ollama or 'not found'}")
    if not ollama:
        print(f"WARN Ollama endpoint/model unavailable: {tags_endpoint} / {model}")
        return False

    result = subprocess.run(
        [ollama, "list"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    has_model = result.returncode == 0 and model in result.stdout
    if has_model:
        print(f"OK   Agent Zero model available: {model}")
        return True

    print(f"WARN Agent Zero model missing: {model}")
    print(f"INFO Expected Ollama endpoint: {tags_endpoint}")
    if ask(f"Pull {model} with Ollama now?", assume_yes):
        return run([ollama, "pull", model])
    return False


def fetch_ollama_models(tags_endpoint: str) -> set[str] | None:
    try:
        with urllib.request.urlopen(tags_endpoint, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return {str(model.get("name")) for model in data.get("models", []) if model.get("name")}


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


def ensure_project_hook(
    project: str,
    project_config: dict[str, Any],
    config_path: Path,
    assume_yes: bool,
) -> bool:
    project_path = Path(project_config["path"]).expanduser()
    git_dir = project_path / ".git"
    if not git_dir.exists():
        print(f"WARN {project}: no .git directory; post-commit hook skipped")
        return False
    hooks_dir = git_dir / "hooks"
    hook_path = hooks_dir / "post-commit"
    hook_text = build_post_commit_hook(
        project=project,
        python_exe=Path(sys.executable),
        chatboks_root=Path(__file__).resolve().parent,
        config_path=config_path.resolve(),
    )

    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8", errors="replace")
        if existing == hook_text:
            print(f"OK   {project}: ChatBoks post-commit hook already installed")
            return True
        if "ChatBoks managed post-commit hook" not in existing:
            if not ask(f"{project}: replace existing post-commit hook with ChatBoks hook?", assume_yes):
                print(f"SKIP {project}: existing post-commit hook left unchanged")
                return False
            backup = hooks_dir / "post-commit.chatboks-bak"
            backup.write_text(existing, encoding="utf-8")
            print(f"OK   {project}: existing hook backed up to {backup}")

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(hook_text, encoding="utf-8", newline="\n")
    print(f"OK   {project}: ChatBoks post-commit hook installed")
    return True


def build_post_commit_hook(
    project: str,
    python_exe: Path,
    chatboks_root: Path,
    config_path: Path,
) -> str:
    return "\n".join(
        [
            "#!/bin/sh",
            "# ChatBoks managed post-commit hook",
            f"PYTHON={shell_quote(python_exe.as_posix())}",
            f"CHATBOKS_ROOT={shell_quote(chatboks_root.as_posix())}",
            f"CONFIG={shell_quote(config_path.as_posix())}",
            f"PROJECT={shell_quote(project)}",
            '"$PYTHON" "$CHATBOKS_ROOT/hook_post_commit.py" "$PROJECT" --config "$CONFIG" --chatboks-root "$CHATBOKS_ROOT"',
            "exit 0",
            "",
        ]
    )


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def find_codegraph_command() -> Path | None:
    found = shutil.which("codegraph") or shutil.which("codegraph.cmd")
    if found:
        return Path(found)
    npm_root = Path(os.environ.get("APPDATA", "")) / "npm"
    for candidate in (npm_root / "codegraph.cmd", npm_root / "codegraph"):
        if candidate.exists():
            return candidate
    return None


def offer_agent_zero(project: str, project_config: dict[str, Any], assume_yes: bool) -> bool:
    agents = project_config.setdefault("agents", [])
    if "agent_zero" in agents:
        print(f"OK   {project}: Agent Zero already on the team")
        return False
    if ask(f"Agent Zero is available. Add it to the {project} team?", assume_yes):
        agents.insert(0, "agent_zero")
        print(f"OK   {project}: Agent Zero added as first responder")
        return True
    print(f"SKIP {project}: Agent Zero not added")
    return False


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
