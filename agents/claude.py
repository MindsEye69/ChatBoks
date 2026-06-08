from __future__ import annotations

from agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"
    default_adapter_profile = "claude_code_print_v1"
    adapter_profiles = {
        "claude_code_print_v1": ["--print", "--dangerously-skip-permissions"],
    }
    default_args = ["--print", "--dangerously-skip-permissions"]
