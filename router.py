from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.agent_zero import AgentZeroAgent
from agents.antigravity import AntigravityAgent
from agents.claude import ClaudeAgent
from agents.codex import CodexAgent


AGENT_CLASSES = {
    "agent_zero": AgentZeroAgent,
    "claude": ClaudeAgent,
    "codex": CodexAgent,
    "antigravity": AntigravityAgent,
}


class Router:
    def __init__(self, config: dict[str, Any], project: str, project_path: Path) -> None:
        self.config = config
        self.project = project
        self.project_path = project_path
        self.project_config = config["projects"][project]
        self.agent_names = list(self.project_config["agents"])
        self._agents: dict[str, Any] = {}

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

    def route_user_prompt(self, text: str) -> tuple[list[str], str, str | None]:
        """Return the agents that should handle a user prompt.

        A leading @agent prefix is exclusive: @claude only calls Claude,
        @codex only calls Codex, etc. The cleaned prompt is passed onward.
        """
        stripped = text.lstrip()
        if not stripped.startswith("@"):
            return list(self.agent_names), text, None

        first, _, remainder = stripped.partition(" ")
        requested = first[1:].lower()
        aliases = {
            "0": "agent_zero",
            "az": "agent_zero",
            "forge": "agent_zero",
            "zero": "agent_zero",
            "antigrav": "antigravity",
            "agy": "antigravity",
        }
        agent_name = aliases.get(requested, requested)
        if agent_name not in self.config.get("agents", {}) or agent_name not in AGENT_CLASSES:
            return list(self.agent_names), text, None

        cleaned = remainder.strip() or text
        return [agent_name], cleaned, agent_name

    def get_agent(self, agent_name: str):
        if agent_name not in AGENT_CLASSES:
            raise ValueError(f"Unsupported agent: {agent_name}")
        if agent_name not in self.config.get("agents", {}):
            raise ValueError(f"Agent '{agent_name}' is not configured")
        if agent_name not in self._agents:
            agent_config = self.config["agents"][agent_name]
            role = self.load_role(agent_name, agent_config)
            cls = AGENT_CLASSES[agent_name]
            self._agents[agent_name] = cls(self.project_path, agent_config, role)
        return self._agents[agent_name]

    def load_role(self, agent_name: str, agent_config: dict[str, Any]) -> str:
        role_file = agent_config.get("role_file")
        if role_file:
            path = self.project_path / role_file
            if path.exists():
                return path.read_text(encoding="utf-8")
        return (
            f"You are {agent_name} in Chatboks, a human-supervised coding relay. "
            "Collaborate with the other agents, push back when useful, and end with "
            "a >>> control signal when a decision, handoff, completion, question, "
            "or block occurs."
        )
