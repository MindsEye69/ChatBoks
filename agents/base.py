from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


class BaseAgent:
    name = "base"
    default_args: list[str] = []

    def __init__(self, project_path: Path, config: dict[str, Any], role: str) -> None:
        self.project_path = project_path
        self.config = config
        self.role = role
        self.cli = config["cli"]

    def initialize(self, codegraph: str) -> str:
        return f"Codegraph loaded. Ready.\n\n{self.short_codegraph_status(codegraph)}"

    def call(self, context_package: str) -> str:
        prompt = self.build_prompt(context_package, mode="respond")
        return self.run_cli(prompt, timeout=300)

    def reinitialize(self, codegraph: str, summary: str, state: dict[str, Any]) -> str:
        prompt = self.build_prompt(
            "\n\n".join(
                [
                    "[SESSION RESUME]",
                    codegraph,
                    "[COMPRESSED PRIOR CONTEXT]",
                    summary,
                    "[STATE]",
                    json.dumps(state, indent=2),
                ]
            ),
            mode="resume",
        )
        return self.run_cli(prompt, timeout=120)

    def execute(self, context_package: str) -> str:
        prompt = self.build_prompt(context_package, mode="execute")
        return self.run_cli(prompt, timeout=600)

    def build_prompt(self, context: str, mode: str) -> str:
        if mode == "execute":
            instruction = "Execute the approved proposal. Report what changed and end with >>> TASK_COMPLETE or >>> BLOCKED."
        elif mode == "resume":
            instruction = "Resume from the compressed context. Confirm readiness or ask a focused question."
        else:
            instruction = (
                "Respond with analysis or action. If proposing a plan, end with >>> PROPOSAL. "
                "If you need user input, end with >>> QUESTION. If handing off, end with >>> HANDOFF. "
                "If another agent has fully addressed the task and you have nothing materially different "
                "to add, end with >>> SKIP. If complete, end with >>> TASK_COMPLETE. "
                "If blocked, end with >>> BLOCKED."
            )
        return f"{self.role}\n\n{context}\n\n{instruction}\n"

    def command(self) -> list[str]:
        return [self.cli, *self.default_args]

    def run_cli(self, prompt: str, timeout: int = 120) -> str:
        command = self.command()
        use_shell = os.name == "nt"
        run_command = subprocess.list2cmdline(command) if use_shell else command
        env = os.environ.copy()
        env["CHATBOKS"] = "1"
        extra: dict[str, Any] = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE — inherited by child processes
            extra["startupinfo"] = si
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            result = subprocess.run(
                run_command,
                input=prompt,
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

    @staticmethod
    def short_codegraph_status(codegraph: str) -> str:
        for line in codegraph.splitlines():
            if line.startswith("Files ") or line.startswith("[CODEGRAPH] Not available"):
                return line
        return "Codegraph summary included."
