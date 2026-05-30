from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from agents.base import BaseAgent


class AgentZeroAgent(BaseAgent):
    name = "agent_zero"

    def build_prompt(self, context: str, mode: str) -> str:
        max_chars = int(self.config.get("max_prompt_chars", 8000))
        if len(context) > max_chars:
            context = (
                context[:max_chars]
                + "\n\n[TRUNCATED_FOR_AGENT_ZERO]\n"
                + "Agent Zero receives compact context only. Ask Claude or Codex for deep code work."
            )
        return super().build_prompt(context, mode)

    def command(self) -> list[str]:
        forge_agent = self.config.get("forge_agent", "qwen")
        command = [
            self.cli,
            str(forge_agent),
            "--project",
            str(self.project_path),
            "-p",
        ]
        model = self.config.get("model")
        if model:
            command.extend(["--model", str(model)])
        mode = self.config.get("mode")
        if mode:
            command.extend(["--mode", str(mode)])
        # TODO: Verify Forge agent name/model/mode flags against the installed Forge CLI.
        return command

    def run_cli(self, prompt: str, timeout: int = 120) -> str:
        prompt_path = self.write_prompt_file(prompt)
        prompt_arg = (
            "You are Agent Zero for ChatBoks. Read the full request from "
            f"{prompt_path.name} in the .chatboks folder of this project, then answer it. "
            "End with exactly one ChatBoks control signal."
        )
        command = [*self.command(), prompt_arg]
        use_shell = os.name == "nt"
        run_command = subprocess.list2cmdline(command) if use_shell else command
        env = os.environ.copy()
        env["CHATBOKS"] = "1"
        env["CHATBOKS_AGENT_ZERO"] = "1"
        extra: dict[str, Any] = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            extra["startupinfo"] = si
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            result = subprocess.run(
                run_command,
                capture_output=True,
                text=True,
                cwd=self.project_path,
                encoding="utf-8",
                timeout=timeout,
                shell=use_shell,
                env=env,
                **extra,
            )
        except subprocess.TimeoutExpired:
            return f"CLI call timed out for {self.name} after {timeout} seconds.\n>>> BLOCKED"
        if result.returncode != 0:
            stderr = result.stderr.strip() or "No stderr captured."
            return f"CLI call failed for {self.name}: {stderr}\n>>> BLOCKED"
        return result.stdout.strip() or f"{self.name} returned no output.\n>>> BLOCKED"

    def write_prompt_file(self, prompt: str) -> Path:
        state_dir = self.project_path / ".chatboks"
        state_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = state_dir / "agent_zero_prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        return prompt_path
