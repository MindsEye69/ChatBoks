from __future__ import annotations

from agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"
    # TODO: Verify Claude Code non-interactive flags against the installed CLI.
    default_args = ["--print", "--dangerously-skip-permissions"]
