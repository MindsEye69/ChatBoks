from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.agent_zero import AgentZeroAgent
from agents.antigravity import AntigravityAgent
from agents.claude import ClaudeAgent
from agents.codex import CodexAgent
from trust import load_role_with_approval


AGENT_CLASSES = {
    "agent_zero": AgentZeroAgent,
    "claude": ClaudeAgent,
    "codex": CodexAgent,
    "antigravity": AntigravityAgent,
}


@dataclass(frozen=True)
class RoutingDecision:
    agents: list[str]
    cleaned_prompt: str
    exclusive_agent: str | None = None
    note: str | None = None
    strategy: str = "full_round"


class Router:
    def __init__(self, config: dict[str, Any], project: str, project_path: Path) -> None:
        self.config = config
        self.project = project
        self.project_path = project_path
        self.project_config = config["projects"][project]
        self.agent_names = list(self.project_config["agents"])
        self.direct_agent_names = list(self.project_config.get("direct_agents", []))
        self.default_round_agents = self.normalize_round_agents(
            self.project_config.get("round_agents") or self.project_config.get("default_agents")
        )
        self.role_routes = {
            str(role).strip().lower(): self.normalize_round_agents(agents)
            for role, agents in dict(self.project_config.get("role_routes", {})).items()
        }
        routing_config = self.project_config.get("routing_intelligence") or {}
        self.routing_intelligence_enabled = bool(routing_config.get("enabled"))

    def primary(self) -> str:
        configured = self.project_config.get("primary")
        if configured in self.agent_names:
            return configured
        return self.agent_names[0]

    def after(self, agent_name: str) -> str | None:
        if agent_name not in self.agent_names:
            return self.primary()
        index = self.agent_names.index(agent_name)
        if index + 1 >= len(self.agent_names):
            return "you"
        return self.agent_names[index + 1]

    def route_user_prompt(
        self,
        text: str,
        collaboration_mode: str | None = None,
    ) -> tuple[list[str], str, str | None]:
        decision = self.route_user_prompt_details(text, collaboration_mode)
        return decision.agents, decision.cleaned_prompt, decision.exclusive_agent

    def route_user_prompt_details(
        self,
        text: str,
        collaboration_mode: str | None = None,
    ) -> RoutingDecision:
        """Return the agents that should handle a user prompt.

        A leading @agent prefix is exclusive: @claude only calls Claude,
        @codex only calls Codex, etc. The cleaned prompt is passed onward.
        """
        stripped = text.lstrip()
        if not stripped.startswith("@"):
            auto = self.auto_route_prompt(text, collaboration_mode)
            if auto is not None:
                return auto
            return RoutingDecision(self.normal_round_agents(collaboration_mode), text)

        first, _, remainder = stripped.partition(" ")
        requested = first[1:].lower()
        if requested in {"all", "team", "everyone"}:
            cleaned = remainder.strip() or text
            return RoutingDecision(list(self.agent_names), cleaned, strategy="explicit_all")

        aliases = {
            "0": "agent_zero",
            "agent0": "agent_zero",
            "az": "agent_zero",
            "forge": "agent_zero",
            "zero": "agent_zero",
            "antigrav": "antigravity",
            "agy": "antigravity",
        }
        agent_name = aliases.get(requested, requested)
        if agent_name not in self.config.get("agents", {}) or agent_name not in AGENT_CLASSES:
            return RoutingDecision(self.normal_round_agents(collaboration_mode), text)
        if agent_name not in self.agent_names and agent_name not in self.direct_agent_names:
            return RoutingDecision(self.normal_round_agents(collaboration_mode), text)

        cleaned = remainder.strip() or text
        return RoutingDecision([agent_name], cleaned, agent_name, strategy="explicit_agent")

    def normal_round_agents(self, collaboration_mode: str | None = None) -> list[str]:
        role = str(collaboration_mode or "").strip().lower()
        if role:
            routed = self.role_routes.get(role)
            if routed:
                return list(routed)
        return self.default_round_agents or list(self.agent_names)

    def normalize_round_agents(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        allowed = set(self.agent_names)
        normalized: list[str] = []
        for item in value:
            name = str(item).strip()
            if name in allowed and name not in normalized:
                normalized.append(name)
        return normalized

    def auto_route_prompt(
        self,
        text: str,
        collaboration_mode: str | None = None,
    ) -> RoutingDecision | None:
        if not self.routing_intelligence_enabled:
            return None

        lowered = " ".join(text.lower().split())
        if not lowered:
            return None

        if self.should_route_to_agent_zero(lowered, collaboration_mode):
            return RoutingDecision(
                ["agent_zero"],
                text,
                note="Routing intelligence: lightweight setup/status request -> Agent Zero.",
                strategy="agent_zero_direct",
            )

        if self.should_route_to_codex(lowered, collaboration_mode):
            return RoutingDecision(
                ["codex"],
                text,
                note="Routing intelligence: implementation-style request -> Codex first.",
                strategy="single_agent_codex",
            )

        if self.should_route_to_claude(lowered, collaboration_mode):
            return RoutingDecision(
                ["claude"],
                text,
                note="Routing intelligence: analysis-heavy request -> Claude first.",
                strategy="single_agent_claude",
            )
        return None

    def should_route_to_agent_zero(
        self,
        lowered: str,
        collaboration_mode: str | None,
    ) -> bool:
        if "agent_zero" not in self.direct_agent_names and "agent_zero" not in self.agent_names:
            return False
        if collaboration_mode in {"brainstorm", "review", "bugsearch"}:
            return False
        if len(lowered) > 220:
            return False
        if self.contains_any(
            lowered,
            (
                "implement ",
                "fix ",
                "patch ",
                "refactor ",
                "write test",
                "add test",
                "run test",
                "review code",
                "security review",
                "threat model",
                "architecture",
                "design a",
                "commit ",
                "push ",
            ),
        ):
            return False
        return self.contains_any(
            lowered,
            (
                "what's next",
                "whats next",
                "what is next",
                "next step",
                "status",
                "routing policy",
                "which agent",
                "who should handle",
                "project setup",
                "check this project setup",
                "diagnostic command",
                "doctor.py",
                "why is claude",
                "why is codex",
                "why is agent_zero",
                "why is antigravity",
                "current mode",
                "context mode",
            ),
        )

    def should_route_to_codex(
        self,
        lowered: str,
        collaboration_mode: str | None,
    ) -> bool:
        if "codex" not in self.agent_names:
            return False
        if collaboration_mode in {"brainstorm", "review", "bugsearch"}:
            return False
        if self.contains_any(lowered, ("options", "tradeoff", "trade-off", "compare", "brainstorm")):
            return False
        if self.contains_any(lowered, ("architecture", "security review", "threat model")):
            return False
        return self.contains_any(
            lowered,
            (
                "implement",
                "fix",
                "patch",
                "refactor",
                "wire up",
                "add test",
                "write test",
                "update code",
                "change the code",
                "make the change",
                "commit",
                "push",
                "start the next thing",
                "proceed as you see fit",
            ),
        )

    def should_route_to_claude(
        self,
        lowered: str,
        collaboration_mode: str | None,
    ) -> bool:
        if "claude" not in self.agent_names:
            return False
        if collaboration_mode in {"brainstorm", "bugsearch"}:
            return False
        if self.contains_any(lowered, ("implement", "fix", "patch", "refactor", "commit", "push")):
            return False
        return self.contains_any(
            lowered,
            (
                "review the design",
                "review the architecture",
                "architecture review",
                "threat model",
                "security review",
                "explain how",
                "why does",
                "analyze the design",
                "analyse the design",
            ),
        )

    @staticmethod
    def contains_any(text: str, needles: tuple[str, ...]) -> bool:
        return any(needle in text for needle in needles)

    def get_agent(self, agent_name: str):
        if agent_name not in AGENT_CLASSES:
            raise ValueError(f"Unsupported agent: {agent_name}")
        if agent_name not in self.config.get("agents", {}):
            raise ValueError(f"Agent '{agent_name}' is not configured")
        agent_config = dict(self.config["agents"][agent_name])
        agent_config["project_name"] = self.project
        role = self.load_role(agent_name, agent_config)
        cls = AGENT_CLASSES[agent_name]
        return cls(self.project_path, agent_config, role)

    def load_role(self, agent_name: str, agent_config: dict[str, Any]) -> str:
        role_file = agent_config.get("role_file")
        if role_file:
            # Project-local role file: requires trust approval before loading.
            approved = load_role_with_approval(self.project_path, role_file)
            if approved is not None:
                return approved
            # Fall back to the installed role file in the chatboks source directory.
            # Installed files are under ChatBoks control, so no approval needed.
            fallback = Path(__file__).parent / Path(role_file).name
            if fallback.exists():
                return fallback.read_text(encoding="utf-8")
        return (
            f"You are {agent_name} in Chatboks, a human-supervised coding relay. "
            "Collaborate with the other agents, push back when useful, and end with "
            "a >>> control signal when a decision, handoff, completion, question, "
            "or block occurs."
        )
