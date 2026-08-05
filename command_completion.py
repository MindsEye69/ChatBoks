from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompletionCatalog:
    modes: dict[str, str]
    agents: dict[str, str]
    agent_statuses: dict[str, str]
    usage_providers: dict[str, str]
    skills: dict[str, str]
    routes: dict[str, str]
    approval_agents: tuple[str, ...]


CONTEXT_CHOICES = {
    "lean": "small context package",
    "normal": "standard context package",
    "full": "maximum broad context",
}
HELP_CHOICES = {
    "compact": "show compact command strip once",
    "pin": "show command strip before prompts",
    "unpin": "hide command strip before prompts",
}
SLEEP_CHOICES = {
    "status": "show latest session memory",
    "show": "show latest session memory",
    "latest": "show latest session memory",
    "run": "consolidate session memory",
    "now": "consolidate session memory",
}
TEST_CHOICES = {
    "confirmation-risk": "local confirmation packet risk smoke",
    "packet-risk": "alias for confirmation-risk",
    "claude-auth": "check Claude Code auth state",
}
TICKET_CHOICES = {
    "open": "show open Paper Sleuth tickets",
    "all": "show all Paper Sleuth tickets",
}
INTEGRATION_CHOICES = {
    "pending": "show pending proof-verified integration requests",
    "all": "show all local integration requests and execution state",
}
ROOT_COMMANDS = {
    "/help": "show the local command guide",
    "/resume": "show project, graph, memory, and session readiness",
    "/health": "show passive trajectory health for the current or latest task",
    "/tickets": "show Paper Sleuth tickets for this project",
    "/integration": "review local verified integration requests",
    "/context": "show or set the agent context size",
    "/consult": "ask one agent for a bounded second opinion",
    "/sleep": "save a durable session checkpoint",
    "/session": "run the optional DasDashboard workflow",
    "/agent": "show or change agent availability",
    "/graph": "show CodeGraph and Graphify status",
    "/model-commands": "list model-specific executable commands",
    "/mode": "show or set the collaboration mode",
    "/test": "run a local diagnostic",
    "/usage": "show or capture provider usage",
    "/latency": "show recent CLI latency",
    "/wins": "show recorded collaboration wins",
    "/failures": "show recorded collaboration failures",
    "/outcomes": "show recorded collaboration outcomes",
    "/dismiss": "discard the active proposal",
}
OUTCOME_CHOICES = {
    "win": "record a positive collaboration outcome",
    "failure": "record a failed collaboration outcome",
}
SESSION_CHOICES = {
    "start": "run DasDashboard start checks",
    "close": "run DasDashboard close checks",
}
AGENT_STATUS_CHOICES = {
    "available": "ready for normal routing",
    "low": "usable but constrained",
    "exhausted": "temporarily skip this agent",
    "blocked": "unavailable until fixed",
    "ready": "alias for available",
    "awake": "alias for available",
    "wake": "alias for available",
}


def catalog_for_chatboks(chatboks: Any) -> CompletionCatalog:
    import orchestrator

    config = getattr(chatboks, "config", {}) or {}
    project_config = getattr(chatboks, "proj_config", {}) or {}
    configured_agents = config.get("agents", {}) if isinstance(config, dict) else {}
    if configured_agents:
        agents = {str(agent): "configured agent" for agent in sorted(configured_agents)}
    else:
        names = list(project_config.get("agents", [])) + list(project_config.get("direct_agents", []))
        agents = {str(agent): "configured agent" for agent in sorted(set(names))}

    modes = {
        str(mode): str(instruction).split(".")[0].strip() or "collaboration mode"
        for mode, instruction in orchestrator.COLLABORATION_MODES.items()
    }
    modes.update({"reset": "alias for default", "standard": "alias for default"})

    providers = {
        str(key): str(value.get("label") or key)
        for key, value in orchestrator.USAGE_PROVIDERS.items()
    }
    configured_providers = config.get("usage_providers", {}) if isinstance(config, dict) else {}
    for key, value in configured_providers.items():
        providers[str(key)] = str(value.get("label") or key) if isinstance(value, dict) else str(key)
    providers["all"] = "sync every known provider"

    try:
        native_skills = chatboks.list_native_skills()
    except Exception:
        native_skills = []
    skills = {str(name): str(summary or "native workflow skill") for name, summary in native_skills}

    routes = {
        "@all": "route to all configured main agents",
        "@triad": "brainstorm with Claude, Codex, and Coordinator, then synthesize",
        "@spark": "route to Codex Spark",
        "@agy": "route to Antigravity",
    }
    routes.update({f"@{agent}": "route directly to agent" for agent in agents})

    approval_agents: list[str] = []
    project_agents = list(project_config.get("agents", []))
    direct_agents = list(project_config.get("direct_agents", []))
    for agent in project_agents + direct_agents:
        if agent in approval_agents or agent not in configured_agents:
            continue
        if agent in project_agents or configured_agents.get(agent, {}).get("can_fill_main_seat"):
            approval_agents.append(str(agent))

    return CompletionCatalog(
        modes=modes,
        agents=agents,
        agent_statuses=dict(AGENT_STATUS_CHOICES),
        usage_providers=providers,
        skills=skills,
        routes=routes,
        approval_agents=tuple(approval_agents),
    )


def completion_options(value: str, catalog: CompletionCatalog) -> list[tuple[str, str]]:
    stripped = value.lstrip()
    upper = stripped.upper()
    if upper == "APPROVE" or upper.startswith("APPROVE "):
        return complete_approval(stripped, catalog.approval_agents)
    if not stripped.startswith(("/", "@")):
        return []

    parts = stripped.split()
    trailing_space = stripped.endswith(" ")
    command = parts[0].lower() if parts else stripped.lower()
    if len(parts) <= 1:
        direct_modes = {
            f"/{mode}": f"set collaboration mode: {label}"
            for mode, label in catalog.modes.items()
        }
        if command in direct_modes:
            return []
        mode_matches = [
            (replacement, label)
            for replacement, label in sorted(direct_modes.items())
            if replacement.startswith(command)
        ]
        subcommand_roots = {
            "/mode",
            "/modes",
            "/context",
            "/ctx",
            "/help",
            "/h",
            "/?",
            "/sleep",
            "/memory",
            "/test",
            "/tests",
            "/ticket",
            "/tickets",
            "/integration",
            "/outcome",
            "/session",
            "/skills",
            "/skill",
            "/usage",
            "/agent",
            "/agents",
        }
        if command not in subcommand_roots:
            root_matches = [
                (replacement, label)
                for replacement, label in sorted(ROOT_COMMANDS.items())
                if replacement.startswith(command) and replacement != command
            ]
            matches = mode_matches + root_matches
            if matches:
                return matches
    if command in {"/mode", "/modes"}:
        return complete_word(stripped, "/mode", catalog.modes)
    if command in {"/context", "/ctx"}:
        return complete_word(stripped, "/context", CONTEXT_CHOICES)
    if command in {"/help", "/h", "/?"}:
        return complete_word(stripped, "/help", HELP_CHOICES)
    if command in {"/sleep", "/memory"}:
        return complete_word(stripped, command, SLEEP_CHOICES)
    if command in {"/test", "/tests"}:
        return complete_word(stripped, "/test", TEST_CHOICES)
    if command in {"/ticket", "/tickets"}:
        return complete_word(stripped, "/tickets", TICKET_CHOICES)
    if command == "/integration":
        return complete_word(stripped, "/integration", INTEGRATION_CHOICES)
    if command == "/outcome":
        return complete_word(stripped, "/outcome", OUTCOME_CHOICES)
    if command == "/session":
        return complete_word(stripped, "/session", SESSION_CHOICES)
    if command in {"/skills", "/skill"}:
        return complete_word(stripped, "/skills", catalog.skills)
    if command == "/usage":
        return complete_usage(parts, trailing_space, catalog.usage_providers)
    if command in {"/agent", "/agents"}:
        return complete_agent(parts, trailing_space, catalog.agents, catalog.agent_statuses)
    if stripped.startswith("@") and len(parts) <= 1:
        prefix = stripped[1:].lower()
        return [(route, label) for route, label in sorted(catalog.routes.items()) if route[1:].startswith(prefix)]
    return []


def complete_word(stripped: str, command: str, choices: dict[str, str]) -> list[tuple[str, str]]:
    parts = stripped.split()
    trailing_space = stripped.endswith(" ")
    if len(parts) == 1 and not trailing_space:
        prefix = ""
    elif len(parts) <= 2:
        prefix = "" if trailing_space else parts[1].lower()
    else:
        return []
    if prefix in choices:
        return []
    return [
        (f"{command} {choice}", description)
        for choice, description in sorted(choices.items())
        if choice.startswith(prefix)
    ]


def complete_approval(stripped: str, agents: tuple[str, ...]) -> list[tuple[str, str]]:
    parts = stripped.split()
    if len(parts) > 2:
        return []
    if len(parts) == 1 and not stripped.endswith(" "):
        return [("APPROVE", "execute with default agent")]
    prefix = parts[1].lstrip("@").lower() if len(parts) > 1 else ""
    return [
        (f"APPROVE {agent}", "execute approved build with this agent")
        for agent in agents
        if agent.startswith(prefix)
    ]


def complete_usage(
    parts: list[str],
    trailing_space: bool,
    providers: dict[str, str],
) -> list[tuple[str, str]]:
    first_choices = {"sync": "capture provider usage baseline", "status": "show saved usage baselines"}
    if 2 <= len(parts) <= 3 and parts[1].lower() == "sync":
        prefix = "" if trailing_space or len(parts) == 2 else parts[2].lower()
        if prefix in providers:
            return []
        return [
            (f"/usage sync {provider}", label)
            for provider, label in sorted(providers.items())
            if provider.startswith(prefix)
        ]
    if len(parts) == 1 and not trailing_space:
        return [(f"/usage {choice}", label) for choice, label in first_choices.items()]
    if len(parts) <= 2:
        prefix = "" if trailing_space else parts[1].lower()
        if prefix in first_choices:
            return []
        return [
            (f"/usage {choice}", label)
            for choice, label in sorted(first_choices.items())
            if choice.startswith(prefix)
        ]
    return []


def complete_agent(
    parts: list[str],
    trailing_space: bool,
    agents: dict[str, str],
    statuses: dict[str, str],
) -> list[tuple[str, str]]:
    if len(parts) == 1:
        return [(f"/agent {agent}", label) for agent, label in sorted(agents.items())]
    if len(parts) <= 2 and not trailing_space:
        prefix = parts[1].lower()
        if prefix in agents:
            return []
        return [
            (f"/agent {agent}", label)
            for agent, label in sorted(agents.items())
            if agent.startswith(prefix)
        ]
    if len(parts) <= 3:
        agent = parts[1].lower() if len(parts) > 1 else ""
        if agent not in agents:
            return []
        prefix = "" if trailing_space else parts[2].lower()
        if prefix in statuses:
            return []
        return [
            (f"/agent {agent} {status}", label)
            for status, label in sorted(statuses.items())
            if status.startswith(prefix)
        ]
    return []
