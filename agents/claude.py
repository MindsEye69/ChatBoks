from __future__ import annotations

from agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"
    default_adapter_profile = "claude_code_print_v1"
    adapter_profiles = {
        "claude_code_print_v1": ["--print", "--dangerously-skip-permissions"],
        "claude_code_plan_v1": ["--print", "--permission-mode", "plan"],
        "claude_code_workspace_v1": ["--print", "--permission-mode", "acceptEdits"],
    }
    default_args = ["--print", "--dangerously-skip-permissions"]
