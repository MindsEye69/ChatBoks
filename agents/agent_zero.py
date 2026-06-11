from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from agents.base import BaseAgent


class AgentZeroAgent(BaseAgent):
    name = "agent_zero"
    signals = ("TASK_COMPLETE", "QUESTION", "BLOCKED")
    role_call_requests = {"role call", "roll call", "rolecall", "rollcall"}
    next_step_markers = ("what's next", "whats next", "what is next", "next step", "what should i test next")

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
            "Reply in concise plain text. Prefer one concrete next action grounded in "
            "the provided context over broad category questions. For setup checks, give one "
            "concrete next diagnostic command when possible. Valid local commands include "
            "/help, /agent, /mode, /context, /usage, /suggest-outcome, /wins, /failures, "
            "and /outcomes. For environment checks, prefer python doctor.py <project> or "
            "/agent. For model-switch validation, prefer @zero role call or @zero what's next "
            "for ChatBoks? as the next check. Do not suggest /context unless the user is "
            "explicitly asking about context mode. Do not invent commands such as /status. "
            "Use >>> QUESTION only when you "
            "include a specific question for the human in the response body. For outcome-scoring "
            "requests, suggest concrete /win or /fail commands but do not pretend to record them. "
            "If deep implementation, architecture, security "
            "review, vision, browser testing, or git work is needed, recommend the right agent "
            "instead of pretending to do it. End with exactly one ChatBoks signal: "
            ">>> TASK_COMPLETE, >>> QUESTION, or >>> BLOCKED."
        )
        return f"{self.role}\n\n[AGENT TURN INSTRUCTION]\n{instruction}\n\n{context}\n"

    def command(self) -> list[str]:
        return [str(self.config.get("cli", "ollama"))]

    def call(self, context_package: str) -> str:
        current_request = self.extract_current_request(context_package)
        lowered_request = current_request.lower()
        if self.is_role_call_request(current_request):
            return self.role_call_response()
        if self.is_next_step_request(lowered_request):
            return self.next_step_response(lowered_request)
        return super().call(context_package)

    def configured_model(self) -> str:
        return str(self.config.get("model", "gemma3:4b"))

    def endpoint(self) -> str:
        return str(self.config.get("endpoint", "http://127.0.0.1:11434/api/chat"))

    @staticmethod
    def tags_endpoint(endpoint: str) -> str:
        return endpoint.replace("/api/chat", "/api/tags").replace("/api/generate", "/api/tags")

    @staticmethod
    def _is_loopback_endpoint(endpoint: str) -> bool:
        try:
            host = (urllib.parse.urlparse(endpoint).hostname or "").strip().lower()
            if not host:
                return False
            if host == "localhost":
                return True
            try:
                return ipaddress.ip_address(host).is_loopback
            except ValueError:
                return False
        except Exception:
            return False

    def run_cli(
        self,
        prompt: str,
        timeout: int = 120,
        idle_timeout: float | None = None,
        max_timeout: float | None = None,
    ) -> str:
        _ = idle_timeout
        current_request = self.extract_current_request(prompt)
        if self.is_role_call_request(current_request):
            return self.role_call_response()
        endpoint = self.endpoint()
        if not self._is_loopback_endpoint(endpoint):
            return (
                f"Agent Zero endpoint '{endpoint}' is not a loopback address. "
                "Only localhost, 127.x.x.x, or ::1 endpoints are permitted.\n>>> BLOCKED"
            )
        model = self.configured_model()
        payload = {
            "model": model,
            "think": self.config.get("think", False),
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Agent Zero in ChatBoks. Plain text only. No JSON. "
                        "No markdown fences. No tool calls. Prefer one concrete next action "
                        "grounded in the provided context over broad category questions. "
                        "For setup checks, provide one concrete next diagnostic command when "
                        "possible. Valid local commands include /help, /agent, /mode, /context, "
                        "/usage, /suggest-outcome, /wins, /failures, and /outcomes. For "
                        "environment checks, prefer python doctor.py <project> or /agent. For "
                        "model-switch validation, prefer @zero role call or @zero what's next "
                        "for ChatBoks? as the next check. Do not suggest /context unless the "
                        "user is explicitly asking about context mode. Do not invent commands "
                        "such as /status. Use >>> QUESTION only with a "
                        "specific question in the body. For outcome-scoring requests, suggest "
                        "concrete /win or /fail commands but do not claim they were recorded. "
                        "End with exactly one of >>> TASK_COMPLETE, >>> QUESTION, or >>> BLOCKED."
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
            request_timeout = max_timeout if max_timeout is not None else timeout
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
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
                if line.strip() and line.strip() not in signal_lines and not line.strip().startswith(">>>")
            ]
            body = self.rewrite_guidance("\n".join(body_lines).strip(), prompt)
            if not body and signal in {"QUESTION", "TASK_COMPLETE"}:
                return self.fallback_for_bare_signal(prompt)
            return f"{body}\n>>> {signal}" if body else f">>> {signal}"
        signal_lines = {f">>> {candidate}" for candidate in self.signals}
        body_lines = [
            line.strip()
            for line in cleaned.splitlines()
            if (
                line.strip()
                and line.strip() not in self.signals
                and line.strip() not in signal_lines
                and not line.strip().startswith(">>>")
            )
        ]
        body = self.rewrite_guidance("\n".join(body_lines).strip(), prompt)
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
        current_request = self.extract_current_request(prompt)
        lowered = current_request.lower()
        if self.is_role_call_request(current_request):
            return self.role_call_response()
        if self.is_model_switch_validation_request(lowered):
            return (
                "Next check: run @zero role call once and confirm Agent Zero answers promptly "
                "on the lighter model without suggesting nonexistent commands.\n>>> TASK_COMPLETE"
            )
        if self.is_next_step_request(lowered):
            return self.next_step_response(lowered)
        if "routing policy" in lowered:
            return (
                "- Normal prompts go to the configured default round agents for the project.\n"
                "- Direct routes like @claude, @codex, or @zero go only to that named agent.\n"
                "- @all opts into the full configured non-direct project team for one prompt.\n"
                "- Exhausted main agents may be substituted with eligible available fallbacks, with a visible system note.\n"
                "- Direct-only agents such as Agent Zero stay quiet unless tagged directly or selected as an eligible fallback.\n"
                ">>> TASK_COMPLETE"
            )
        if "diagnostic command" in lowered or "check this project setup" in lowered:
            project_match = re.search(r"\bProject:\s*([A-Za-z0-9_-]+)", current_request)
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

    def rewrite_guidance(self, body: str, prompt: str) -> str:
        if not body:
            return body
        current_request = self.extract_current_request(prompt)
        lowered_request = current_request.lower()
        lowered_body = body.lower()
        if self.is_role_call_request(current_request):
            normalized = " ".join(lowered_body.split())
            if normalized in {"run: /agent", "/agent"} or normalized.startswith("/agent "):
                return self.role_call_response().removesuffix("\n>>> TASK_COMPLETE")
        if self.is_next_step_request(lowered_request):
            normalized = " ".join(lowered_body.split())
            if normalized in {"run: /agent", "/agent"} or normalized.startswith("/agent "):
                return self.next_step_response(lowered_request).removesuffix("\n>>> TASK_COMPLETE")
            if "/context" in lowered_body or "context before proceeding" in lowered_body:
                if self.is_model_switch_validation_request(lowered_request):
                    return (
                        "Next check: run @zero role call once and confirm Agent Zero answers "
                        "promptly on gemma3:4b without UI lag or invented commands."
                    )
                return self.next_step_response(lowered_request).removesuffix("\n>>> TASK_COMPLETE")
        if "/status" in lowered_body:
            body = re.sub(r"(?i)/status", "/agent", body)
            lowered_body = body.lower()
        if self.is_model_switch_validation_request(lowered_request):
            if "/context" in lowered_body or "context before proceeding" in lowered_body:
                return (
                    "Next check: run @zero role call once and confirm Agent Zero answers "
                    "promptly on gemma3:4b without UI lag or invented commands."
                )
        return body

    @staticmethod
    def is_model_switch_validation_request(lowered_request: str) -> bool:
        return (
            ("test next" in lowered_request or "validate next" in lowered_request or "what should i test next" in lowered_request)
            and ("switch" in lowered_request or "gemma3:4b" in lowered_request or "lighter model" in lowered_request)
        )

    def is_next_step_request(self, lowered_request: str) -> bool:
        return any(marker in lowered_request for marker in self.next_step_markers)

    def is_role_call_request(self, request: str) -> bool:
        normalized = " ".join(request.strip().lower().split())
        return normalized in self.role_call_requests

    def next_step_response(self, lowered_request: str) -> str:
        if self.is_model_switch_validation_request(lowered_request):
            return (
                "Next test: run @zero role call, then @zero what's next for ChatBoks? "
                "Confirm both answers are concrete, fast, and do not suggest nonexistent "
                "commands such as /status.\n>>> TASK_COMPLETE"
            )
        if "test" in lowered_request:
            return (
                "Next test: run the smallest smoke for the most recent change, then route "
                "any failure to Codex with the exact error text. For Agent Zero specifically, "
                "use @zero role call and @zero what's next for ChatBoks? as the quick quality checks.\n"
                ">>> TASK_COMPLETE"
            )
        if "chatboks" in lowered_request or "project" in lowered_request:
            return (
                "Next ChatBoks step: continue the smallest active validation item, then hand "
                "implementation or git work to Codex. Quick check first: run /agent to confirm "
                "availability before starting a longer round.\n>>> TASK_COMPLETE"
            )
        return (
            "Next step: pick one scoped validation or diagnostic, keep Agent Zero on status/routing, "
            "and route implementation or repo edits to Codex. Run /agent first if availability is unclear.\n"
            ">>> TASK_COMPLETE"
        )

    def role_call_response(self) -> str:
        model = self.configured_model()
        endpoint = self.endpoint()
        if not self._is_loopback_endpoint(endpoint):
            status_line = (
                f"Agent Zero configured for Ollama model `{model}`, but the endpoint is blocked by loopback policy: {endpoint}."
            )
        else:
            tags_endpoint = self.tags_endpoint(endpoint)
            try:
                with urllib.request.urlopen(tags_endpoint, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                models = {str(item.get("name")) for item in data.get("models", []) if item.get("name")}
                if model in models:
                    status_line = f"Agent Zero online. Local coordinator ready via Ollama model `{model}`."
                else:
                    status_line = (
                        f"Agent Zero configured for Ollama model `{model}`, but that model is not currently available in Ollama."
                    )
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                status_line = (
                    f"Agent Zero configured for Ollama model `{model}`, but the local Ollama runtime did not answer a readiness check."
                )
        return (
            f"{status_line}\n"
            "I handle lightweight setup checks, routing, summaries, and simple status questions.\n"
            "Use /agent to inspect availability or @zero for a direct local diagnostic.\n"
            ">>> TASK_COMPLETE"
        )

    @staticmethod
    def extract_current_request(prompt: str) -> str:
        marker = "[ACTIVE TASK]"
        index = prompt.rfind(marker)
        if index == -1:
            return prompt
        section = prompt[index + len(marker):].lstrip("\r\n")
        next_section = re.search(r"\n\[[A-Z][A-Z0-9 _-]*\]", section)
        if next_section:
            section = section[: next_section.start()]
        return section.strip()

    def write_prompt_file(self, prompt: str) -> Path:
        state_dir = self.project_path / ".chatboks"
        state_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = state_dir / "agent_zero_prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        return prompt_path
