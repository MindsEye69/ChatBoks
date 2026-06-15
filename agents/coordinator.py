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


class CoordinatorAgent(BaseAgent):
    name = "coordinator"
    signals = ("TASK_COMPLETE", "QUESTION", "BLOCKED")
    role_call_requests = {"role call", "roll call", "rolecall", "rollcall"}
    join_requests = {"join", "join in", "jump in", "step in", "come in"}
    next_step_markers = ("what's next", "whats next", "what is next", "next step", "what should i test next")

    @property
    def project_name(self) -> str:
        return str(self.config.get("project_name") or "").strip()

    def build_prompt(self, context: str, mode: str) -> str:
        max_chars = int(self.config.get("max_prompt_chars", 8000))
        if len(context) > max_chars:
            context = (
                context[:max_chars]
                + "\n\n[TRUNCATED_FOR_COORDINATOR]\n"
                + "Coordinator receives compact context only. Ask Claude or Codex for deep code work."
            )
        instruction = (
            "You are Coordinator for ChatBoks: a local, cheap coordinator for setup, "
            "diagnostics, routing, summaries, and small status checks. You do not have tools. "
            "Do not emit JSON, markdown fences, fake tool calls, or END_OF_MESSAGE. "
            "Reply in concise plain text. Prefer one concrete next action grounded in "
            "the provided context over broad category questions. For setup checks, give one "
            "concrete next diagnostic command when possible. Valid local commands include "
            "/help, /agent, /mode, /context, /usage, /suggest-outcome, /wins, /failures, "
            "and /outcomes. For environment checks, prefer python doctor.py <project> or "
            "/agent. For model-switch validation, prefer @coordinator role call or @coordinator what's next "
            "for ChatBoks? as the next check. Do not suggest /context unless the user is "
            "explicitly asking about context mode. Do not invent commands such as /status. "
            "For summaries, diffs, resume packets, or planning reviews, include the key evidence "
            "when present: files changed, tests run, risks, and the next action. "
            "Use >>> QUESTION only when the response body contains a direct question the human "
            "must answer. If you are giving a recommendation, status, or next action without a "
            "human question, use >>> TASK_COMPLETE. For outcome-scoring "
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
        if self.is_join_request(current_request):
            return self.join_response()
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
        if self.is_join_request(current_request):
            return self.join_response()
        endpoint = self.endpoint()
        if not self._is_loopback_endpoint(endpoint):
            return (
                f"Coordinator endpoint '{endpoint}' is not a loopback address. "
                "Only localhost, 127.x.x.x, or ::1 endpoints are permitted.\n>>> BLOCKED"
            )
        model = self.configured_model()
        payload = {
            "model": model,
            "think": self.config.get("think", False),
            "stream": True,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Coordinator in ChatBoks. Plain text only. No JSON. "
                        "No markdown fences. No tool calls. Prefer one concrete next action "
                        "grounded in the provided context over broad category questions. "
                        "For setup checks, provide one concrete next diagnostic command when "
                        "possible. Valid local commands include /help, /agent, /mode, /context, "
                        "/usage, /suggest-outcome, /wins, /failures, and /outcomes. For "
                        "environment checks, prefer python doctor.py <project> or /agent. For "
                        "model-switch validation, prefer @coordinator role call or @coordinator what's next "
                        "for ChatBoks? as the next check. Do not suggest /context unless the "
                        "user is explicitly asking about context mode. Do not invent commands "
                        "such as /status. For summaries, diffs, resume packets, or planning "
                        "reviews, include key evidence when present: files changed, tests run, "
                        "risks, and the next action. Use >>> QUESTION only when the response "
                        "body contains a direct question the human must answer. If you are "
                        "giving a recommendation, status, or next action without a human "
                        "question, use >>> TASK_COMPLETE. For outcome-scoring requests, suggest "
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
                content, raw = self.read_ollama_response(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return f"Ollama call failed for {self.name}: HTTP {exc.code} {detail}\n>>> BLOCKED"
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            return f"Ollama call failed for {self.name}: {exc}\n>>> BLOCKED"

        if content is not None:
            return self.normalize_output(content, prompt)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return f"Ollama returned invalid JSON for {self.name}: {raw[:500]}\n>>> BLOCKED"

        content = (data.get("message") or {}).get("content") or data.get("response") or ""
        return self.normalize_output(str(content), prompt)

    def read_ollama_response(self, response: Any) -> tuple[str | None, str]:
        raw_parts: list[str] = []
        content_parts: list[str] = []
        if hasattr(response, "readline"):
            while True:
                raw_line = response.readline()
                if raw_line and not isinstance(raw_line, (bytes, bytearray)):
                    raw = response.read().decode("utf-8", errors="replace")
                    return None, raw
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                raw_parts.append(line)
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    return None, "\n".join(raw_parts)
                delta = str((item.get("message") or {}).get("content") or item.get("response") or "")
                if delta:
                    content_parts.append(delta)
                    if self.stdout_callback is not None:
                        self.stdout_callback(delta)
            return "".join(content_parts), "\n".join(raw_parts)

        raw = response.read().decode("utf-8", errors="replace")
        raw_parts.append(raw)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) <= 1:
            return None, raw
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                return None, raw
            delta = str((item.get("message") or {}).get("content") or item.get("response") or "")
            if delta:
                content_parts.append(delta)
                if self.stdout_callback is not None:
                    self.stdout_callback(delta)
        return "".join(content_parts), raw

    def normalize_output(self, text: str, prompt: str = "") -> str:
        cleaned = text.strip().replace("END_OF_MESSAGE", "").strip()
        if not cleaned:
            return f"{self.name} returned no output.\n>>> BLOCKED"
        if self.looks_like_tool_call(cleaned):
            return (
                "Coordinator attempted to emit a tool call instead of plain text. "
                "Retry with a smaller diagnostic request or route to Codex.\n>>> BLOCKED"
            )
        signal_positions = [
            (cleaned.rfind(f">>> {candidate}"), candidate)
            for candidate in self.signals
            if f">>> {candidate}" in cleaned
        ]
        signal = max(signal_positions)[1] if signal_positions else None
        if signal:
            before_signal, _, after_signal = cleaned.rpartition(f">>> {signal}")
            signal_lines = {f">>> {candidate}" for candidate in self.signals}
            body_lines = [
                line.strip()
                for line in f"{before_signal}\n{after_signal}".splitlines()
                if line.strip() and line.strip() not in signal_lines and not line.strip().startswith(">>>")
            ]
            body = self.rewrite_guidance("\n".join(body_lines).strip(), prompt)
            if not body and signal in {"QUESTION", "TASK_COMPLETE"}:
                return self.fallback_for_bare_signal(prompt)
            if signal == "QUESTION" and not self.body_has_direct_question(body):
                signal = "TASK_COMPLETE"
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

    @staticmethod
    def body_has_direct_question(body: str) -> bool:
        if "?" in body:
            return True
        question_starters = (
            "what ",
            "which ",
            "who ",
            "where ",
            "when ",
            "why ",
            "how ",
            "can you ",
            "could you ",
            "should i ",
            "should we ",
            "do you ",
            "would you ",
            "is there ",
            "are there ",
        )
        for line in body.splitlines():
            normalized = line.strip().lower()
            if any(normalized.startswith(starter) for starter in question_starters):
                return True
        return False

    def fallback_for_bare_signal(self, prompt: str) -> str:
        current_request = self.extract_current_request(prompt)
        lowered = current_request.lower()
        if self.is_role_call_request(current_request):
            return self.role_call_response()
        if self.is_join_request(current_request):
            return self.join_response()
        if self.is_model_switch_validation_request(lowered):
            return (
                "Next check: run @coordinator role call once and confirm Coordinator answers promptly "
                "on the lighter model without suggesting nonexistent commands.\n>>> TASK_COMPLETE"
            )
        if self.is_next_step_request(lowered):
            return self.next_step_response(lowered)
        if "routing policy" in lowered:
            return (
                "- Normal prompts go to the configured default round agents for the project.\n"
                "- Direct routes like @claude, @codex, or @coordinator go only to that named agent.\n"
                "- @all opts into the full configured non-direct project team for one prompt.\n"
                "- Exhausted main agents may be substituted with eligible available fallbacks, with a visible system note.\n"
                "- Direct-only agents such as Coordinator stay quiet unless tagged directly or selected as an eligible fallback.\n"
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
            "Coordinator returned a bare control signal without an actionable response. "
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
                        "Next check: run @coordinator role call once and confirm Coordinator answers "
                        "promptly on gemma3:4b without UI lag or invented commands."
                    )
                return self.next_step_response(lowered_request).removesuffix("\n>>> TASK_COMPLETE")
        if "/status" in lowered_body:
            body = re.sub(r"(?i)/status", "/agent", body)
            lowered_body = body.lower()
        if self.is_system_noise_request(lowered_request) and not self.recommends_hidden_diagnostics(lowered_body):
            return (
                "Default the remote view to actual agent answers first. Hide system and bridge diagnostics "
                "behind the System and Bridge controls unless the user explicitly opens them, and keep the "
                "latest response/copy actions focused on the agent answer."
            )
        if self.is_exhausted_lane_request(lowered_request) and not self.recommends_live_lane_fallback(lowered_body):
            return (
                "Keep the three lanes reserved for live working agents. When Claude is exhausted, hide "
                "Claude's lane, promote an eligible fallback such as Codex Spark or Gemma into that slot, "
                "and restore Claude while demoting the fallback once the exhaustion reset expires."
            )
        if self.is_model_switch_validation_request(lowered_request):
            if "/context" in lowered_body or "context before proceeding" in lowered_body:
                return (
                    "Next check: run @coordinator role call once and confirm Coordinator answers "
                    "promptly on gemma3:4b without UI lag or invented commands."
                )
        return body

    @staticmethod
    def is_system_noise_request(lowered_request: str) -> bool:
        return (
            "route" not in lowered_request
            and ("system" in lowered_request or "bridge" in lowered_request)
            and ("noise" in lowered_request or "mixed" in lowered_request or "separate" in lowered_request)
            and ("agent" in lowered_request or "answer" in lowered_request or "response" in lowered_request)
        )

    @staticmethod
    def recommends_hidden_diagnostics(lowered_body: str) -> bool:
        return (
            ("hide" in lowered_body or "hidden" in lowered_body)
            and ("system" in lowered_body or "bridge" in lowered_body)
        )

    @staticmethod
    def is_exhausted_lane_request(lowered_request: str) -> bool:
        return (
            ("exhausted" in lowered_request or "token" in lowered_request)
            and ("lane" in lowered_request or "window" in lowered_request or "slot" in lowered_request)
            and ("claude" in lowered_request or "agent" in lowered_request)
        )

    @staticmethod
    def recommends_live_lane_fallback(lowered_body: str) -> bool:
        return (
            ("hide" in lowered_body or "remove" in lowered_body)
            and ("promote" in lowered_body or "fallback" in lowered_body or "fill" in lowered_body)
            and ("restore" in lowered_body or "return" in lowered_body)
        )

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

    def is_join_request(self, request: str) -> bool:
        normalized = " ".join(request.strip().lower().split())
        return normalized in self.join_requests

    def next_step_response(self, lowered_request: str) -> str:
        if self.is_model_switch_validation_request(lowered_request):
            return (
                "Next test: run @coordinator role call, then @coordinator what's next for ChatBoks? "
                "Confirm both answers are concrete, fast, and do not suggest nonexistent "
                "commands such as /status.\n>>> TASK_COMPLETE"
            )
        if "test" in lowered_request:
            return (
                "Next test: run the smallest smoke for the most recent change, then route "
                "any failure to Codex with the exact error text. For Coordinator specifically, "
                "use @coordinator role call and @coordinator what's next for ChatBoks? as the quick quality checks.\n"
                ">>> TASK_COMPLETE"
            )
        if "chatboks" in lowered_request or "project" in lowered_request:
            return (
                "Next ChatBoks step: continue the smallest active validation item, then hand "
                "implementation or git work to Codex. Quick check first: run /agent to confirm "
                "availability before starting a longer round.\n>>> TASK_COMPLETE"
            )
        return (
            "Next step: pick one scoped validation or diagnostic, keep Coordinator on status/routing, "
            "and route implementation or repo edits to Codex. Run /agent first if availability is unclear.\n"
            ">>> TASK_COMPLETE"
        )

    def join_response(self) -> str:
        return (
            "Coordinator is in. I can handle lightweight routing, setup checks, summaries, and small diagnostics. "
            "For a useful next check, ask @coordinator what's next for ChatBoks? or run /agent to inspect availability.\n"
            ">>> TASK_COMPLETE"
        )

    def role_call_response(self) -> str:
        model = self.configured_model()
        endpoint = self.endpoint()
        if not self._is_loopback_endpoint(endpoint):
            status_line = (
                f"Coordinator configured for Ollama model `{model}`, but the endpoint is blocked by loopback policy: {endpoint}."
            )
        else:
            tags_endpoint = self.tags_endpoint(endpoint)
            try:
                with urllib.request.urlopen(tags_endpoint, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                models = {str(item.get("name")) for item in data.get("models", []) if item.get("name")}
                if model in models:
                    status_line = f"Coordinator online. Local coordinator ready via Ollama model `{model}`."
                else:
                    status_line = (
                        f"Coordinator configured for Ollama model `{model}`, but that model is not currently available in Ollama."
                    )
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                status_line = (
                    f"Coordinator configured for Ollama model `{model}`, but the local Ollama runtime did not answer a readiness check."
                )
        return (
            f"{status_line}\n"
            "I handle lightweight setup checks, routing, summaries, and simple status questions.\n"
            "Use /agent to inspect availability or @coordinator for a direct local diagnostic.\n"
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
        prompt_path = state_dir / "coordinator_prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        return prompt_path
