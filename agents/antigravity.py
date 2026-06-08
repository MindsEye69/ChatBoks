from __future__ import annotations

from agents.base import BaseAgent


class AntigravityAgent(BaseAgent):
    name = "antigravity"
    default_adapter_profile = "agy_run_v1"
    adapter_profiles = {
        "agy_run_v1": ["run", "--no-interactive"],
    }
    default_args = ["run", "--no-interactive"]
