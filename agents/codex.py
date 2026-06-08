from __future__ import annotations

from agents.base import BaseAgent


class CodexAgent(BaseAgent):
    name = "codex"
    default_adapter_profile = "codex_exec_v1"
    adapter_profiles = {
        "codex_exec_v1": [
            "exec",
            "-C",
            "{project_path}",
            "--dangerously-bypass-approvals-and-sandbox",
            "-s",
            "danger-full-access",
            "-",
        ],
    }
    default_args = adapter_profiles["codex_exec_v1"]
