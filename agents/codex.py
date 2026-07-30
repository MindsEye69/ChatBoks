from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


CODEX_MODEL_ALIASES = {
    "gpt-5.6": "gpt-5.6-sol",
}
CODEX_MODEL_CHOICES = ["", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]


def normalize_codex_model(model: str) -> str:
    cleaned = model.strip()
    return CODEX_MODEL_ALIASES.get(cleaned, cleaned)


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

    def command(self, adapter_override: dict[str, Any] | None = None) -> list[str]:
        command = [self.cli, *self.adapter_args(adapter_override)]
        model = normalize_codex_model(str(self.config.get("model") or ""))
        if model:
            command.extend(["--model", model])
        return command


class CodexSparkAgent(CodexAgent):
    name = "codex_spark"
    default_adapter_profile = "codex_spark_exec_v1"
    adapter_profiles = {
        **CodexAgent.adapter_profiles,
        "codex_spark_exec_v1": [
            "exec",
            "-C",
            "{project_path}",
            "-m",
            "gpt-5.3-codex-spark",
            "--dangerously-bypass-approvals-and-sandbox",
            "-s",
            "danger-full-access",
            "-",
        ],
    }
    default_args = adapter_profiles["codex_spark_exec_v1"]
