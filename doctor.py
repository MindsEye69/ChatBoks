#!/usr/bin/env python3
"""ChatBoks doctor: local diagnostics and adapter health checks."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - diagnostic path
    yaml = None

from agents.agent_zero import AgentZeroAgent
from agents.antigravity import AntigravityAgent
from agents.claude import ClaudeAgent
from agents.codex import CodexAgent


AGENT_CLASSES = {
    "agent_zero": AgentZeroAgent,
    "antigravity": AntigravityAgent,
    "claude": ClaudeAgent,
    "codex": CodexAgent,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a ChatBoks install")
    parser.add_argument("project", nargs="?", help="Optional project name from config.yaml")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--smoke-agents", action="store_true", help="Run minimal model calls; may consume tokens")
    args = parser.parse_args()

    ok = True
    print("ChatBoks doctor")
    print("================")

    ok = check_python_deps() and ok

    if yaml is None:
        print("FAIL pyyaml is not installed")
        return 1

    if not args.config.exists():
        print(f"FAIL missing config: {args.config}")
        return 1

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    print(f"OK   config: {args.config}")
    ok = check_node_and_codegraph() and ok

    projects = config.get("projects", {})
    selected = [args.project] if args.project else sorted(projects)
    for project in selected:
        if project not in projects:
            print(f"FAIL unknown project: {project}")
            ok = False
            continue
        ok = check_project(project, projects[project], config, args.smoke_agents) and ok

    return 0 if ok else 1


def check_python_deps() -> bool:
    ok = True
    for module in ("rich", "watchdog", "yaml"):
        present = importlib.util.find_spec(module) is not None
        print(("OK  " if present else "FAIL") + f" python module: {module}")
        ok = ok and present
    return ok


def check_node_and_codegraph() -> bool:
    ok = True
    node = shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    print(("OK  " if node else "WARN") + f" node: {node or 'not found'}")
    print(("OK  " if npm else "WARN") + f" npm: {npm or 'not found'}")
    codegraph = find_command("codegraph")
    print(("OK  " if codegraph else "WARN") + f" codegraph command: {codegraph or 'not found'}")
    if npm:
        installed = npm_package_installed("@colbymchenry/codegraph")
        print(("OK  " if installed else "WARN") + " npm global @colbymchenry/codegraph")
        ok = ok and installed
    else:
        ok = False
    return ok


def check_project(project: str, project_config: dict[str, Any], config: dict[str, Any], smoke_agents: bool) -> bool:
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
        ok = check_agent(project_path, agent_name, agent_config, smoke_agents) and ok

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
    ok = check_project_hook(project_path) and ok
    return ok


def check_project_hook(project_path: Path) -> bool:
    hook_path = project_path / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        print(f"WARN post-commit hook: {hook_path}")
        return True
    text = hook_path.read_text(encoding="utf-8", errors="replace")
    installed = "ChatBoks managed post-commit hook" in text and "hook_post_commit.py" in text
    print(("OK  " if installed else "WARN") + f" post-commit hook: {hook_path}")
    return True


def check_agent(project_path: Path, agent_name: str, agent_config: dict[str, Any], smoke_agents: bool) -> bool:
    if agent_name == "agent_zero":
        return check_agent_zero(agent_config, smoke_agents)

    ok = True
    cli = agent_config.get("cli", agent_name)
    role_file = agent_config.get("role_file")
    cli_path = Path(cli)
    cli_ok = cli_path.exists() or shutil.which(cli) is not None
    print(("OK  " if cli_ok else "FAIL") + f" {agent_name} cli: {cli}")
    ok = ok and cli_ok
    profile = str(agent_config.get("adapter_profile") or "default")
    profile_ok = adapter_profile_known(agent_name, agent_config)
    print(("OK  " if profile_ok else "WARN") + f" {agent_name} adapter profile: {profile}")
    ok = ok and profile_ok

    if role_file:
        role_path = project_path / role_file
        role_ok = role_path.exists()
        print(("OK  " if role_ok else "WARN") + f" {agent_name} role file: {role_path}")

    if cli_ok:
        ok = check_cli_help(cli, agent_name) and ok
        if smoke_agents:
            ok = smoke_agent_stdin(agent_name, project_path, agent_config) and ok
        else:
            print(f"SKIP {agent_name} stdin smoke test (use --smoke-agents; may consume tokens)")
    return ok


def adapter_profile_known(agent_name: str, agent_config: dict[str, Any]) -> bool:
    cls = AGENT_CLASSES.get(agent_name)
    if cls is None:
        return False
    if isinstance(agent_config.get("adapter_args"), list):
        return True
    profile = str(agent_config.get("adapter_profile") or cls.default_adapter_profile)
    return profile == cls.default_adapter_profile or profile in cls.adapter_profiles


def check_agent_zero(agent_config: dict[str, Any], smoke_agents: bool) -> bool:
    ok = True
    cli = agent_config.get("cli", "ollama")
    cli_ok = shutil.which(cli) is not None
    print(("OK  " if cli_ok else "WARN") + f" agent_zero ollama cli: {cli}")

    endpoint = str(agent_config.get("endpoint", "http://127.0.0.1:11434/api/chat"))
    tags_endpoint = endpoint.replace("/api/chat", "/api/tags").replace("/api/generate", "/api/tags")
    model = str(agent_config.get("model", "qwen2.5-coder:3b"))
    models = fetch_ollama_models(tags_endpoint)
    if models is None:
        print(f"FAIL agent_zero ollama endpoint: {tags_endpoint}")
        return False

    print(f"OK   agent_zero ollama endpoint: {tags_endpoint}")
    has_model = model in models
    print(("OK  " if has_model else "FAIL") + f" agent_zero model: {model}")
    ok = ok and has_model

    if smoke_agents and has_model:
        ok = smoke_agent_zero(endpoint, model) and ok
    elif not smoke_agents:
        print("SKIP agent_zero smoke test (use --smoke-agents)")
    return ok


def check_cli_help(cli: str, agent_name: str) -> bool:
    result = run_capture([cli, "--help"], timeout=30)
    ok = result.returncode == 0 and bool(result.stdout or result.stderr)
    print(("OK  " if ok else "WARN") + f" {agent_name} --help")
    return ok


def smoke_agent_stdin(
    agent_name: str,
    project_path: Path,
    agent_config: dict[str, Any],
) -> bool:
    env = os.environ.copy()
    env["CHATBOKS"] = "1"
    if agent_name == "agent_zero":
        return smoke_agent_zero(
            str(agent_config.get("endpoint", "http://127.0.0.1:11434/api/chat")),
            str(agent_config.get("model", "qwen2.5-coder:3b")),
        )
    cls = AGENT_CLASSES.get(agent_name)
    if cls is None:
        print(f"SKIP {agent_name} stdin smoke test: no adapter yet")
        return True
    command = cls(project_path, agent_config, "doctor smoke").command()
    input_text = None if agent_name == "agent_zero" else "Reply with exactly: CHATBOKS_OK"
    result = run_capture(command, input_text=input_text, cwd=project_path, env=env, timeout=60)
    ok = result.returncode == 0 and "CHATBOKS_OK" in (result.stdout or "")
    print(("OK  " if ok else "FAIL") + f" {agent_name} stdin smoke")
    return ok


def fetch_ollama_models(tags_endpoint: str) -> set[str] | None:
    try:
        with urllib.request.urlopen(tags_endpoint, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return {str(model.get("name")) for model in data.get("models", []) if model.get("name")}


def smoke_agent_zero(endpoint: str, model: str) -> bool:
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "Plain text only."},
            {"role": "user", "content": "Reply with exactly: CHATBOKS_OK"},
        ],
        "options": {"temperature": 0, "num_predict": 32},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"FAIL agent_zero ollama smoke ({exc})")
        return False
    output = (data.get("message") or {}).get("content") or data.get("response") or ""
    ok = "CHATBOKS_OK" in output
    print(("OK  " if ok else "FAIL") + " agent_zero ollama smoke")
    return ok


def run_capture(
    command: list[str],
    input_text: str | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    use_shell = os.name == "nt"
    run_command: str | list[str] = subprocess.list2cmdline(command) if use_shell else command
    extra: dict[str, Any] = {}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        extra["startupinfo"] = si
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.run(
            run_command,
            input=input_text,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=timeout,
            shell=use_shell,
            encoding="utf-8",
            **extra,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


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


def find_command(name: str) -> str | None:
    found = shutil.which(name) or shutil.which(f"{name}.cmd")
    if found:
        return found
    npm_root = Path(os.environ.get("APPDATA", "")) / "npm"
    for candidate in (npm_root / f"{name}.cmd", npm_root / name):
        if candidate.exists():
            return str(candidate)
    return None


def npm_package_installed(package: str) -> bool:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        return False
    result = run_capture([npm, "list", "-g", package, "--depth=0", "--json"], timeout=30)
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return package in (data.get("dependencies") or {})


def default_config_path() -> Path:
    local = Path(__file__).resolve().parent / "config.yaml"
    if local.exists():
        return local
    return Path("~/.chatboks/config.yaml").expanduser()


if __name__ == "__main__":
    raise SystemExit(main())
