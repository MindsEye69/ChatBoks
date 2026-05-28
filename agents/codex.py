from __future__ import annotations

from agents.base import BaseAgent


class CodexAgent(BaseAgent):
    name = "codex"

    def command(self) -> list[str]:
        # TODO: Verify Codex CLI flags against the installed CLI.
        return [
            self.cli,
            "exec",
            "-C",
            str(self.project_path),
            "--dangerously-bypass-approvals-and-sandbox",
            "-s",
            "danger-full-access",
            "-",
        ]
