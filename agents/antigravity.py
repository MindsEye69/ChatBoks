from __future__ import annotations

from agents.base import BaseAgent


class AntigravityAgent(BaseAgent):
    name = "antigravity"
    # TODO: Verify Antigravity/agy non-interactive flags against the installed CLI.
    default_args = ["run", "--no-interactive"]
