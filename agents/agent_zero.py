from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agents.base import BaseAgent


class AgentZeroAgent(BaseAgent):
    name = "agent_zero"
    signals = ("TASK_COMPLETE", "QUESTION", "BLOCKED")

    @property
    def project_name(self) -> str:
        return str(self.config.get("project_name") or "").strip()

    def build_prompt(self, context: str, mode: str) -> str:
        max_chars = int(self.config.get("max_prompt_chars", 8000))
        if len(context) > max_chars:
            context = (
                context[:max_chars]
                + "\n\n[TRUNCATED_FOR_AGENT_ZERO]\n"
                + "Agent Zero receives compact context only. Ask Claude or Codex for deep code work."
            )
        instruction = (
            "You are Agent Zero for ChatBoks: a local, cheap coordinator for setup, "
            "diagnostics, routing, summaries, and small status checks. You do not have tools. "
            "Do not emit JSON, markdown fences, fake tool calls, or END_OF_MESSAGE. "
            "Reply in concise plain text. For setup checks, give one concrete next diagnostic "
            "command when possible. Use >>> QUESTION only when you include a specific question "
            "for the human in the response body. If deep implementation, architecture, security "
            "review, vision, browser testing, or git work is needed, recommend the right agent "
            "instead of pretending to do it. End with exactly one ChatBoks signal: "
            ">>> TASK_COMPLETE, >>> QUESTION, or >>> BLOCKED."
        )
        return f"{self.role}\n\n{context}\n\n{instruction}\n"

    def command(self) -> list[str]:
        return [str(self.config.get("cli", "ollama"))]

    def run_cli(self, prompt: str, timeout: int = 120) -> str:
        endpoint = str(self.config.get("endpoint", "http://127.0.0.1:11434/api/chat"))
        model = str(self.config.get("model", "qwen2.5-coder:3b"))
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Agent Zero in ChatBoks. Plain text only. No JSON. "
                        "No markdown fences. No tool calls. For setup checks, provide one "
                        "concrete next diagnostic command when possible. Use >>> QUESTION only "
                        "with a specific question in the body. End with exactly one of "
                        ">>> TASK_COMPLETE, >>> QUESTION, or >>> BLOCKED."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": float(self.config.get("temperature", 0.1)),
                "num_predict": int(self.config.get("num_predict", 512)),
            },
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return f"Ollama call failed for {self.name}: HTTP {exc.code} {detail}\n>>> BLOCKED"
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            return f"Ollama call failed for {self.name}: {exc}\n>>> BLOCKED"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return f"Ollama returned invalid JSON for {self.name}: {raw[:500]}\n>>> BLOCKED"

        content = (data.get("message") or {}).get("content") or data.get("response") or ""
        return self.normalize_output(str(content), prompt)

    def normalize_output(self, text: str, prompt: str = "") -> str:
        cleaned = text.strip().replace("END_OF_MESSAGE", "").strip()
        if not cleaned:
            return f"{self.name} returned no output.\n>>> BLOCKED"
        if self.looks_like_tool_call(cleaned):
            return (
                "Agent Zero attempted to emit a tool call instead of plain text. "
                "Retry with a smaller diagnostic request or route to Codex.\n>>> BLOCKED"
            )
        signal_positions = [
            (cleaned.rfind(f">>> {candidate}"), candidate)
            for candidate in self.signals
            if f">>> {candidate}" in cleaned
        ]
        signal = max(signal_positions)[1] if signal_positions else None
        if signal:
            before_signal, _, _ = cleaned.rpartition(f">>> {signal}")
            signal_lines = {f">>> {candidate}" for candidate in self.signals}
            body_lines = [
                line.strip()
                for line in before_signal.splitlines()
                if line.strip() and line.strip() not in signal_lines
            ]
            body = "\n".join(body_lines).strip()
            if not body and signal in {"QUESTION", "TASK_COMPLETE"}:
                return self.fallback_for_bare_signal(prompt)
            return f"{body}\n>>> {signal}" if body else f">>> {signal}"
        signal_lines = {f">>> {candidate}" for candidate in self.signals}
        body_lines = [
            line.strip()
            for line in cleaned.splitlines()
            if line.strip() and line.strip() not in self.signals and line.strip() not in signal_lines
        ]
        body = "\n".join(body_lines).strip()
        return f"{body}\n>>> TASK_COMPLETE" if body else ">>> TASK_COMPLETE"

    @staticmethod
    def looks_like_tool_call(text: str) -> bool:
        lowered = text.lower()
        return (
            '"arguments"' in lowered
            and '"name"' in lowered
        ) or (
            lowered.startswith("{")
            and ("read_file" in lowered or "tool" in lowered)
        )

    def fallback_for_bare_signal(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "diagnostic command" in lowered or "check this project setup" in lowered:
            project_match = re.search(r"\bProject:\s*([A-Za-z0-9_-]+)", prompt)
            project = project_match.group(1) if project_match else self.project_name
            command = f"python doctor.py {project}" if project else "python doctor.py"
            return (
                f"Next diagnostic command: {command}\n"
                "Run it from the ChatBoks folder. Add --smoke-agents only when you intentionally "
                "want live model calls.\n>>> TASK_COMPLETE"
            )
        return (
            "Agent Zero returned a bare control signal without an actionable response. "
            "Retry the request or route it to Codex.\n>>> BLOCKED"
        )

    def write_prompt_file(self, prompt: str) -> Path:
        state_dir = self.project_path / ".chatboks"
        state_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = state_dir / "agent_zero_prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        return prompt_path
