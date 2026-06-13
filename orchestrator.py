#!/usr/bin/env python3
"""Chatboks orchestrator.

Runs a human-supervised relay between Claude, Codex, and Antigravity using:
- chatboks.md for the readable conversation stream
- .chatboks/state.json for machine-readable session state
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agents.base import AgentTimeoutError, TokenExhaustionError
from context.builder import ContextBuilder
from context.packets import ThoughtPacket, extract_packets, packet_records_from_jsonl, split_observed_by_anchor
from encoding_utils import configure_utf8_stdio, utf8_env
from router import Router, RoutingDecision
from ui.stream import Stream


SIGNALS = [
    "PROPOSAL",
    "QUESTION",
    "HANDOFF",
    "TASK_COMPLETE",
    "TASK COMPLETE",
    "BLOCKED",
    "SKIP",
    "CRITERIA_PENDING",
]


COLLABORATION_MODES = {
    "default": "Standard relay. Follow each agent role, respond naturally, and avoid duplicate work.",
    "brainstorm": (
        "Brainstorm mode. Contribute distinct ideas, options, tradeoffs, and risks. "
        "Avoid premature convergence; build on prior agents only when it adds new value."
    ),
    "bugsearch": (
        "Bugsearch mode. Hunt for concrete defects, missed edge cases, regressions, and test gaps. "
        "Prioritize unique findings with severity, evidence, and likely files."
    ),
    "implement": (
        "Implement mode. Prefer scoped, buildable changes. Codex should focus on patches/tests/git mechanics; "
        "Claude should focus on architecture, risk, and acceptance criteria."
    ),
    "review": (
        "Review mode. Use code-review posture: findings first, ordered by severity, with file/line references "
        "and residual test risk. Avoid broad redesign unless necessary."
    ),
    "confirmation": (
        "Confirmation mode. The responsible model does the work, then a different configured model verifies whether "
        "the requested outcome is actually complete. The verifier should not redo the task; it confirms completion "
        "or sends specific missing work back for a bounded repair pass."
    ),
    "diagnose": (
        "Diagnose mode. Establish the root cause with the smallest useful probes. Recommend concrete commands "
        "or narrow fixes before broad implementation."
    ),
}

CRITERIA_GATE_REASONS = {
    "broad": "broad task",
    "multi_agent": "multi-agent coordination",
    "durable": "durable protocol/memory change",
    "security": "security or remote-access sensitive",
    "ambiguous": "ambiguous completion target",
}

AGENT_STATUSES = {"available", "low", "exhausted", "blocked"}

DEFAULT_AGENT_FALLBACKS = {
    "claude": ["codex", "coordinator"],
    "codex": ["claude", "coordinator"],
    "gemini": ["claude", "codex", "coordinator"],
    "antigravity": ["codex", "claude", "coordinator"],
}

HELP_COMMANDS = [
    ("/help", "Show this command deck."),
    ("/help compact", "Show the compact prompt command strip once."),
    ("/help pin", "Show the compact command strip before each prompt."),
    ("/help unpin", "Stop showing the compact command strip before each prompt."),
    ("/skills", "List native ChatBoks workflow skills."),
    ("/skills <name>", "Preview a workflow skill without calling agents."),
    ("/resume", "Show start-of-session readiness: graphs, memory, packets, git, and next action."),
    ("/context", "Show current context mode: lean, normal, or full."),
    ("/context lean|normal|full", "Set how much context agents receive. Lean is default."),
    ("/sleep", "Close a work block: consolidate memory, sync CodeGraph, and report graph/git state."),
    ("/sleep status", "Show the latest session memory checkpoint."),
    ("/agent", "List agent availability for this project."),
    ("/agent <name> exhausted 50m", "Mark a model exhausted for a timed cooldown."),
    ("/agent <name> available", "Mark a model available again."),
    ("/graph", "Show CodeGraph and Graphify freshness."),
    ("/model-commands", "List registered model-specific executable commands."),
    ("/mode", "Show the current collaboration mode and available modes."),
    ("/mode <name>", "Set prompt framing: default, brainstorm, bugsearch, implement, review, confirmation, diagnose."),
    ("/test confirmation-risk", "Run a local no-agent smoke for confirmation packet risk gating."),
    ("/win ...", "Record a collaboration win without calling agents."),
    ("/fail ...", "Record a collaboration failure without calling agents."),
    ("/suggest-outcome [agent]", "Ask Coordinator for candidate /win or /fail lines from recent work."),
    ("/outcomes", "Show recent wins and failures."),
    ("/usage", "Show saved provider usage baselines and available sync targets."),
    ("/usage sync <provider>", "Open a provider usage dashboard, capture a screenshot, and save a baseline."),
    ("/latency", "Show recent agent CLI latency splits."),
    ("@claude / @codex / @spark / @coordinator", "Route the next prompt exclusively to one agent."),
    ("@all ...", "Opt into the full configured non-direct project team for one prompt."),
    ("APPROVE / MODIFY / REJECT", "Respond to a proposal gate."),
    ("/dismiss", "Discard the active proposal without executing it."),
    ("exit / quit / bye", "End the ChatBoks terminal session."),
]

HELP_PIN_COMMANDS = [
    "/help",
    "/skills",
    "/resume",
    "/context",
    "/sleep",
    "/agent",
    "/graph",
    "/model-commands",
    "/mode",
    "/test",
    "/usage",
    "/latency",
    "/win",
    "/fail",
    "/outcomes",
    "/dismiss",
    "@all",
    "@claude",
    "@codex",
    "@spark",
    "@coordinator",
    "exit",
]

USAGE_PROVIDERS = {
    "anthropic": {
        "label": "Anthropic Console",
        "url": "https://console.anthropic.com/settings/usage",
    },
    "openai": {
        "label": "OpenAI Platform",
        "url": "https://platform.openai.com/usage",
    },
    "google": {
        "label": "Google AI Studio",
        "url": "https://aistudio.google.com/",
    },
}

ROLE_CALL_REQUESTS = {"role call", "roll call", "rolecall", "rollcall"}
DIRECT_AGENT_ALIASES = {
    "coordinator": "@coordinator",
    "codex_spark": "@spark",
    "antigravity": "@agy",
}

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class ChatboksFileHandler(FileSystemEventHandler):
    """Watch chatboks.md for external handoff changes."""

    def __init__(self, app: "Chatboks") -> None:
        self.app = app
        self._last_event = 0.0

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return
        if Path(event.src_path) != self.app.chatboks_md:
            return
        now = time.time()
        if now - self._last_event < 0.5:
            return
        self._last_event = now
        self.app.handle_external_update()


class Chatboks:
    def __init__(
        self,
        project: str,
        trigger: str = "manual",
        config_path: Path | None = None,
    ) -> None:
        self.project = project
        self.trigger = trigger
        self.config = self.load_config(config_path)
        if project not in self.config.get("projects", {}):
            known = ", ".join(sorted(self.config.get("projects", {}).keys()))
            raise SystemExit(f"Unknown project '{project}'. Known projects: {known}")

        self.proj_config = self.config["projects"][project]
        self.proj_path = Path(self.proj_config["path"]).expanduser().resolve()
        self.chatboks_md = self.proj_path / "chatboks.md"
        self.state_file = self.proj_path / ".chatboks" / "state.json"
        self.packet_file = self.proj_path / ".chatboks" / "packets.jsonl"
        self.stream = Stream(self.config.get("agents", {}), self.proj_config["agents"])
        self.router = Router(self.config, project, self.proj_path)
        self.context = ContextBuilder(self.proj_path, self.config)
        self.state = self.normalize_state(self.load_state())
        self._internal_write = False
        self.input_buffer: list[str] = []
        self._streamed_agent_responses: dict[str, str] = {}

    def start(self, watch: bool = False, once: bool = False) -> None:
        self.ensure_project_files()
        self.stream.intro(self.project)
        if self.state.get("status") == "initializing":
            self.initialize_agents()
        self.stream.ready()
        self.refresh_token_usage_display()

        if self.state.get("status") == "handoff":
            self.stream.system("Pending handoff detected.")
            self.handle_handoff()
            if once or self.trigger == "commit":
                return

        if self.trigger == "commit":
            self.handle_commit_trigger()
            return

        if once:
            self.run_agent_round()
            return

        if watch:
            self.run_with_watcher()
            return

        self.run_input_loop()

    def initialize_agents(self) -> None:
        codegraph = self.context.load_codegraph()
        self.stream.role_call(
            self.proj_config["agents"],
            standby_agents=self.direct_standby_agents(self.proj_config["agents"]),
        )
        for agent_name in self.proj_config["agents"]:
            self.stream.system(f"Initializing {agent_name}...")
            agent = self.router.get_agent(agent_name)
            response = agent.initialize(codegraph)
            self.append_message(agent_name, response)
        self.update_state({"status": "active", "next_agent": self.router.primary()})

    def run_input_loop(self) -> None:
        while True:
            try:
                if not self.input_buffer:
                    self.show_prompt_help_pin()
                user_input = self.stream.prompt("... > " if self.input_buffer else "You > ")
                if not user_input.strip() and not self.input_buffer:
                    continue
                user_input = self.buffer_or_complete_input(user_input)
                if user_input is None:
                    continue
                if user_input.lower().strip() in {"exit", "quit", "bye"}:
                    self.stream.system("Session ended.")
                    self.update_state({"status": "idle"})
                    break
                self.handle_user_input(user_input)
            except KeyboardInterrupt:
                self.stream.system("Session paused.")
                self.update_state({"status": "paused"})
                break

    def run_with_watcher(self) -> None:
        observer = Observer()
        handler = ChatboksFileHandler(self)
        observer.schedule(handler, str(self.proj_path), recursive=False)
        observer.start()
        self.stream.system(f"Watching {self.chatboks_md}")
        try:
            self.run_input_loop()
        finally:
            observer.stop()
            observer.join()

    def handle_user_input(self, text: str) -> None:
        if self.handle_local_command(text):
            return
        if not self.ensure_session_token_budget():
            return

        prior_status = self.state.get("status")
        self.append_message("you", text)

        if prior_status == "awaiting_approval":
            self.handle_approval(text)
            return
        if prior_status == "awaiting_criteria":
            self.handle_criteria_response(text)
            return

        decision = self.router.route_user_prompt_details(
            text,
            collaboration_mode=self.state.get("collaboration_mode"),
        )
        agents = decision.agents
        routed_text = decision.cleaned_prompt
        exclusive_agent = decision.exclusive_agent
        if decision.note:
            self.append_message("system", decision.note)
        if exclusive_agent:
            escaped = self.model_command_escape_text(routed_text)
            if escaped is not None:
                routed_text = escaped
            elif self.handle_model_command_if_present(exclusive_agent, routed_text):
                return
            else:
                note = self.model_command_wrong_owner_note(exclusive_agent, routed_text)
                if note:
                    self.append_message("system", note)
                    routed_text = f"[MODEL COMMAND NOTE]\n{note}\n\n{routed_text}"
        agents = self.resolve_available_agents(agents, exclusive_agent)
        if not agents:
            return
        if self.should_gate_acceptance_criteria(text, agents, decision):
            self.handle_criteria_pending(text, routed_text, agents, exclusive_agent, decision)
            return
        self.start_routed_agent_round(routed_text, agents, exclusive_agent)

    def start_routed_agent_round(
        self,
        routed_text: str,
        agents: list[str],
        exclusive_agent: str | None = None,
    ) -> None:
        next_agent = exclusive_agent or agents[0]
        self.update_state(
            {
                "status": "active",
                "next_agent": next_agent,
                "active_task": routed_text,
                "agent_status": self.load_agent_statuses(),
                "confirmation_repairs_used": 0,
                "handoff_depth": 0,
                "criteria_gate": None,
            }
        )
        self.run_agent_round(initiator=routed_text, agents=agents)

    def should_gate_acceptance_criteria(
        self,
        text: str,
        agents: list[str],
        decision: RoutingDecision,
    ) -> bool:
        if not self.criteria_gate_enabled():
            return False
        if decision.exclusive_agent:
            return False
        return bool(self.criteria_gate_reasons(text, agents, decision))

    def criteria_gate_enabled(self) -> bool:
        gate_config = self.config.get("criteria_gate", {})
        if isinstance(gate_config, dict) and gate_config.get("enabled") is False:
            return False
        return True

    def criteria_gate_reasons(
        self,
        text: str,
        agents: list[str],
        decision: RoutingDecision,
    ) -> list[str]:
        del decision
        lowered = " ".join(text.lower().split())
        if not lowered:
            return []
        reasons: list[str] = []
        if len(agents) > 1 and self.contains_any(
            lowered,
            (
                "all agents",
                "everyone",
                "team",
                "round",
                "rounds",
                "debate",
                "converge",
                "consensus",
                "top improvement",
                "top improvements",
            ),
        ):
            reasons.append("multi_agent")
        if len(lowered) > 240 or self.contains_any(
            lowered,
            (
                "roadmap",
                "architecture",
                "design",
                "overhaul",
                "broad",
                "strategy",
                "plan",
                "speed things up",
                "top improvement",
                "top improvements",
            ),
        ):
            reasons.append("broad")
        if self.contains_any(
            lowered,
            (
                "protocol",
                "memory",
                "sleep",
                "summar",
                "packet",
                "handoff",
                "routing",
                "mode",
                "runbook",
                "docs",
                "documentation",
            ),
        ):
            reasons.append("durable")
        if self.contains_any(
            lowered,
            (
                "security",
                "auth",
                "token",
                "secret",
                "password",
                "remote",
                "pairing",
                "tailscale",
                "firewall",
                "serve",
                "network",
                "shell",
                "execute",
            ),
        ):
            reasons.append("security")
        if self.contains_any(
            lowered,
            (
                "make it better",
                "improve it",
                "whatever is next",
                "what's next",
                "whats next",
                "proceed as planned",
                "their plan",
            ),
        ):
            reasons.append("ambiguous")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def contains_any(text: str, needles: tuple[str, ...]) -> bool:
        return any(needle in text for needle in needles)

    def handle_criteria_pending(
        self,
        original_text: str,
        routed_text: str,
        agents: list[str],
        exclusive_agent: str | None,
        decision: RoutingDecision,
    ) -> None:
        reasons = self.criteria_gate_reasons(original_text, agents, decision)
        gate = {
            "id": f"criteria_{int(time.time())}",
            "original_text": original_text,
            "routed_text": routed_text,
            "agents": agents,
            "exclusive_agent": exclusive_agent,
            "strategy": decision.strategy,
            "mode": self.state.get("collaboration_mode", "default"),
            "reasons": reasons,
        }
        self.update_state(
            {
                "status": "awaiting_criteria",
                "next_agent": "you",
                "active_task": routed_text,
                "criteria_gate": gate,
            }
        )
        message = self.format_criteria_gate(gate)
        self.append_message("system", f"{message}\n>>> CRITERIA_PENDING")
        self.stream.proposal(message)
        self.stream.system("Type APPROVE to run, MODIFY <criteria> to add detail, or REJECT to cancel.")

    def handle_criteria_response(self, text: str) -> None:
        gate = self.state.get("criteria_gate")
        if not isinstance(gate, dict):
            self.stream.system("No pending criteria gate. Treating input as a new prompt.")
            self.update_state({"status": "idle", "criteria_gate": None})
            self.handle_user_input(text)
            return

        verdict = text.strip().upper()
        if verdict in {"APPROVE", "YES", "Y", "OK", "GO"}:
            agents = [str(agent) for agent in gate.get("agents") or []]
            if not agents:
                self.stream.system("Criteria gate lost its routed agents. Please resend the prompt.")
                self.update_state({"status": "blocked", "next_agent": "you", "criteria_gate": None})
                return
            self.stream.system("Criteria approved. Running agents...")
            self.start_routed_agent_round(
                str(gate.get("routed_text") or gate.get("original_text") or ""),
                agents,
                str(gate.get("exclusive_agent") or "") or None,
            )
            return
        if verdict == "REJECT":
            self.stream.system("Criteria gate rejected. Awaiting next instruction.")
            self.update_state({"status": "idle", "active_task": None, "criteria_gate": None, "next_agent": "you"})
            return

        modification = self.normalize_modification(text)
        gate["routed_text"] = "\n".join(
            [
                str(gate.get("routed_text") or gate.get("original_text") or ""),
                "",
                "[ACCEPTANCE CRITERIA]",
                modification,
            ]
        )
        self.update_state({"criteria_gate": gate})
        self.stream.proposal(self.format_criteria_gate(gate))
        self.stream.system("Criteria updated. Type APPROVE to run or REJECT to cancel.")

    def format_criteria_gate(self, gate: dict[str, Any]) -> str:
        reasons = [
            CRITERIA_GATE_REASONS.get(str(reason), str(reason))
            for reason in gate.get("reasons", [])
        ]
        agents = ", ".join(str(agent) for agent in gate.get("agents", [])) or "unknown"
        lines = [
            "CRITERIA_PENDING",
            "Acceptance criteria gate triggered before agent execution.",
            f"Triggers: {', '.join(reasons) or 'unspecified'}",
            f"Mode: {gate.get('mode') or 'default'}",
            f"Routing: {gate.get('strategy') or 'default'} -> {agents}",
            "Minimum acceptance criteria:",
            "- Desired outcome is explicit enough that agents can verify completion.",
            "- Safety, auth, remote access, or durable memory impact is named when relevant.",
            "- Verification evidence is expected before TASK_COMPLETE.",
        ]
        routed_text = str(gate.get("routed_text") or "")
        if "[ACCEPTANCE CRITERIA]" in routed_text:
            lines.append("User criteria appended to the prompt.")
        return "\n".join(lines)

    def handle_local_command(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return False

        command = stripped.split(maxsplit=1)[0].lower()
        if command in {"/help", "/h", "/?"}:
            self.handle_help_command(stripped)
            return True
        if command in {"/skill", "/skills"}:
            self.handle_skills_command(stripped)
            return True
        if command in {"/win", "/fail", "/outcome"}:
            self.handle_outcome_command(stripped)
            return True
        if command == "/usage":
            self.handle_usage_command(stripped)
            return True
        if command == "/latency":
            self.handle_latency_command(stripped)
            return True
        if command in {"/suggest-outcome", "/suggest-outcomes"}:
            self.handle_outcome_suggestion_command(stripped)
            return True
        if command in {"/wins", "/failures", "/outcomes"}:
            outcome_type = {
                "/wins": "win",
                "/failures": "failure",
            }.get(command)
            self.show_outcomes(outcome_type=outcome_type)
            return True
        if command in {"/mode", "/modes"}:
            self.handle_mode_command(stripped)
            return True
        if command == "/resume":
            self.handle_resume_command()
            return True
        if command in {"/context", "/ctx"}:
            self.handle_context_command(stripped)
            return True
        if command in {"/sleep", "/memory"}:
            self.handle_sleep_command(stripped)
            return True
        if command in {"/agent", "/agents"}:
            self.handle_agent_command(stripped)
            return True
        if command in {"/graph", "/graphs"}:
            self.handle_graph_command()
            return True
        if command in {"/model-commands", "/model-command", "/model-cmds"}:
            self.handle_model_commands_command()
            return True
        if command in {"/test", "/tests"}:
            self.handle_test_command(stripped)
            return True
        if command == "/dismiss":
            self.handle_dismiss_command()
            return True

        self.stream.system(
            "Unknown local command. Try /help, /skills, /resume, /context, /sleep, /agent, /graph, /model-commands, /mode, /test confirmation-risk, /usage, /latency, /win, /fail, /outcome, /wins, /failures, /outcomes, or /dismiss."
        )
        return True

    def handle_help_command(self, text: str = "/help") -> None:
        parts = text.split(maxsplit=1)
        action = parts[1].strip().lower() if len(parts) > 1 else ""
        if action in {"pin", "pinned", "on"}:
            self.update_state({"help_pin": True})
            self.stream.system("Pinned prompt help is on. Use /help unpin to hide it.")
            return
        if action in {"unpin", "off", "hide"}:
            self.update_state({"help_pin": False})
            self.stream.system("Pinned prompt help is off. Use /help pin to show it again.")
            return
        if action in {"compact", "mini"}:
            self.show_prompt_help_pin(force=True)
            return
        if action:
            self.stream.system("Unknown /help option. Try /help, /help compact, /help pin, or /help unpin.")
            return
        if hasattr(self.stream, "help_box"):
            self.stream.help_box(HELP_COMMANDS)
            return
        lines = ["ChatBoks commands:"]
        lines.extend(f"- {command}: {description}" for command, description in HELP_COMMANDS)
        self.stream.system("\n".join(lines))

    def show_prompt_help_pin(self, force: bool = False) -> None:
        if not force and not self.state.get("help_pin", True):
            return
        if hasattr(self.stream, "help_pin"):
            self.stream.help_pin(HELP_PIN_COMMANDS)
            return
        self.stream.system("Commands: " + "  ".join(HELP_PIN_COMMANDS))

    def handle_model_commands_command(self) -> None:
        lines = ["Registered model commands:"]
        found = False
        for agent_name in sorted(self.config.get("agents", {})):
            for command in self.agent_model_commands(agent_name):
                found = True
                aliases = ", ".join(command["aliases"])
                status = "enabled" if command.get("enabled", True) else "disabled"
                description = command.get("description") or "No description."
                lines.append(f"- {agent_name}: {command['name']} ({status}); aliases: {aliases}; {description}")
        if not found:
            lines.append("- none")
        self.stream.system("\n".join(lines))

    def handle_test_command(self, text: str) -> None:
        parts = text.strip().split()
        target = parts[1].lower() if len(parts) > 1 else ""
        if target not in {"confirmation-risk", "packet-risk"}:
            self.stream.system("Available local tests:\n- /test confirmation-risk")
            return

        executor_response = "\n".join(
            [
                "No-edit local smoke.",
                ">>> PACKET",
                "agent: codex",
                "stance: VERIFY",
                "observed:",
                "- no files edited",
                "risks:",
                "- missing explicit verifier acknowledgement",
                "next_action: verifier must acknowledge risk",
                "signal: TASK_COMPLETE",
                ">>> PACKET_END",
                ">>> TASK_COMPLETE",
            ]
        )
        checklist = "\n".join(self.confirmation_packet_checklist_lines(executor_response, "codex"))
        ignored_risks = self.unresolved_packet_risks(executor_response, "confirmed complete\n>>> TASK_COMPLETE", "codex")
        addressed_risks = self.unresolved_packet_risks(
            executor_response,
            "Risk reviewed and accepted: missing explicit verifier acknowledgement.\n>>> TASK_COMPLETE",
            "codex",
        )

        checks = [
            ("packet checklist includes observed fact", "no files edited" in checklist),
            (
                "packet checklist includes actionable risk",
                "missing explicit verifier acknowledgement" in checklist,
            ),
            (
                "bare verifier completion is rejected",
                ignored_risks == ["missing explicit verifier acknowledgement"],
            ),
            ("explicit verifier acknowledgement is accepted", addressed_risks == []),
        ]
        failed = [name for name, passed in checks if not passed]
        lines = ["Confirmation packet-risk local smoke:"]
        lines.extend(f"- {'PASS' if passed else 'FAIL'}: {name}" for name, passed in checks)
        lines.append("- No agents called; no files edited.")
        if failed:
            lines.append(">>> BLOCKED")
        else:
            lines.append(">>> TASK_COMPLETE")
        self.stream.system("\n".join(lines))

    def handle_model_command_if_present(self, agent_name: str, text: str) -> bool:
        escaped = self.model_command_escape_text(text)
        if escaped is not None:
            return False

        match = self.find_agent_model_command(agent_name, text)
        if match is None:
            return False

        command, args = match
        if not command.get("enabled", True):
            self.append_message("system", f"Model command {command['name']} for {agent_name} is disabled.")
            return True
        if command.get("type") != "cli_subcommand":
            self.append_message(
                "system",
                f"Model command {command['name']} for {agent_name} has unsupported type: {command.get('type')}.",
            )
            return True

        available = self.resolve_available_agents([agent_name], agent_name)
        if not available:
            return True

        self.update_state(
            {
                "status": "active",
                "next_agent": agent_name,
                "active_task": f"model command: {command['name']}",
                "agent_status": self.load_agent_statuses(),
            }
        )
        try:
            response = self.execute_model_cli_subcommand(agent_name, command, args)
        except AgentTimeoutError as exc:
            partial = f"{exc.partial_output.rstrip()}\n" if exc.partial_output else ""
            response = f"{partial}{exc}\n>>> BLOCKED"
        except TokenExhaustionError as exc:
            response = f"{exc}\n>>> BLOCKED"
        except Exception as exc:
            response = f"Model command {command['name']} for {agent_name} failed: {exc}\n>>> BLOCKED"
        if response.strip() and self.parse_signal(response) is None:
            response = f"{response.rstrip()}\n>>> TASK_COMPLETE"
        self.append_message(agent_name, response)
        self.update_token_count(agent_name, response)
        self.update_state({"status": "idle", "next_agent": "you", "last_agent": agent_name, "active_task": None})
        return True

    def model_command_wrong_owner_note(self, agent_name: str, text: str) -> str | None:
        escaped = self.model_command_escape_text(text)
        if escaped is not None:
            return None
        token, _ = self.model_command_token_and_args(text)
        if not token:
            return None
        for owner in sorted(self.config.get("agents", {})):
            if owner == agent_name:
                continue
            for command in self.agent_model_commands(owner):
                if token in command["normalized_aliases"]:
                    owner_alias = DIRECT_AGENT_ALIASES.get(owner, f"@{owner}")
                    return (
                        f"Model command hint: `{token}` belongs to {owner}, not {agent_name}; "
                        f"it was not executed. Use {owner_alias} /{command['name']} ... to run it."
                    )
        return None

    @staticmethod
    def model_command_escape_text(text: str) -> str | None:
        stripped = text.lstrip()
        if stripped == "--":
            return ""
        if stripped.startswith("-- "):
            return stripped[3:].lstrip()
        return None

    def find_agent_model_command(self, agent_name: str, text: str) -> tuple[dict[str, Any], list[str]] | None:
        token, args_text = self.model_command_token_and_args(text)
        if not token:
            return None
        for command in self.agent_model_commands(agent_name):
            if token in command["normalized_aliases"]:
                return command, self.split_model_command_args(args_text)
        return None

    @staticmethod
    def model_command_token_and_args(text: str) -> tuple[str | None, str]:
        stripped = text.strip()
        if not stripped:
            return None, ""
        first, _, rest = stripped.partition(" ")
        token = first.removeprefix("/").strip().lower()
        if not token:
            return None, ""
        return token, rest.strip()

    def agent_model_commands(self, agent_name: str) -> list[dict[str, Any]]:
        agent_config = self.config.get("agents", {}).get(agent_name, {})
        raw_commands = agent_config.get("model_commands") or []
        if not isinstance(raw_commands, list):
            return []
        commands: list[dict[str, Any]] = []
        for raw in raw_commands:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip().lower().removeprefix("/")
            if not name:
                continue
            aliases = raw.get("aliases") or []
            if not isinstance(aliases, list):
                aliases = []
            alias_values = [name]
            alias_values.extend(str(alias).strip() for alias in aliases if str(alias).strip())
            normalized_aliases = sorted({alias.removeprefix("/").lower() for alias in alias_values})
            command = dict(raw)
            command["name"] = name
            command["aliases"] = [f"/{alias}" for alias in normalized_aliases]
            command["normalized_aliases"] = normalized_aliases
            command.setdefault("enabled", True)
            commands.append(command)
        return commands

    @staticmethod
    def split_model_command_args(args_text: str) -> list[str]:
        if not args_text:
            return []
        try:
            return shlex.split(args_text)
        except ValueError:
            return args_text.split()

    def execute_model_cli_subcommand(self, agent_name: str, command: dict[str, Any], args: list[str]) -> str:
        agent = self.router.get_agent(agent_name)
        argv = self.model_command_argv(command, args)
        if not argv:
            return f"Model command {command['name']} has no argv configured.\n>>> BLOCKED"
        return agent.run_cli_once(
            "",
            [agent.cli, *argv],
            timeout=float(command.get("timeout", 300) or 300),
            max_timeout=float(command.get("max_timeout", 900) or 900),
        )

    def model_command_argv(self, command: dict[str, Any], args: list[str]) -> list[str]:
        raw_argv = command.get("argv") or []
        if not isinstance(raw_argv, list):
            return []
        argv: list[str] = []
        joined_args = " ".join(args)
        for item in raw_argv:
            part = str(item)
            if part == "{args}":
                argv.extend(args)
            else:
                argv.append(part.format(project_path=str(self.proj_path), args=joined_args))
        return argv

    def handle_resume_command(self) -> None:
        lines = ["Resume readiness:"]
        lines.extend(self.resume_project_lines())
        lines.extend(self.resume_git_lines())
        lines.extend(self.codegraph_status_lines())
        graphify_lines = self.graphify_status_lines()
        lines.extend(graphify_lines)
        sleep_lines, has_sleep_memory = self.sleep_memory_status_lines()
        lines.extend(sleep_lines)
        lines.extend(self.packet_status_lines())
        lines.extend(self.resume_session_lines())
        lines.extend(self.resume_next_action_lines(graphify_lines, has_sleep_memory))
        self.stream.system("\n".join(lines))

    def resume_project_lines(self) -> list[str]:
        return [
            f"- Project: {self.project}",
            f"  Path: {self.proj_path}",
        ]

    def resume_git_lines(self) -> list[str]:
        branch_result = self.run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        status_result = self.run_git(["status", "--porcelain"])
        if branch_result.returncode != 0 or status_result.returncode != 0:
            reason = (branch_result.stderr or status_result.stderr or "git unavailable").strip()
            return [f"- Git: WARN, {reason}"]
        branch = (branch_result.stdout or "").strip() or "unknown"
        changes = [line for line in (status_result.stdout or "").splitlines() if line.strip()]
        if not changes:
            return [f"- Git: {branch}, clean"]
        return [f"- Git: {branch}, dirty ({len(changes)} pending changes)"]

    def sleep_memory_status_lines(self) -> tuple[list[str], bool]:
        metadata_path = self.sleep_dir() / "latest.json"
        latest_path = self.sleep_latest_path()
        if not metadata_path.exists() and not latest_path.exists():
            return (["- Sleep memory: none yet. Run /sleep at a work break."], False)
        if not metadata_path.exists():
            return ([f"- Sleep memory: present at {latest_path}, metadata missing"], True)
        try:
            record = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            return ([f"- Sleep memory: WARN, could not read {metadata_path}: {exc}"], True)
        timestamp = record.get("timestamp") or "unknown time"
        items = record.get("items")
        item_text = f"{items} items" if isinstance(items, int) else "unknown item count"
        summary_path = record.get("summary_path") or str(latest_path)
        return (
            [
                f"- Sleep memory: {item_text}, last consolidated {timestamp}",
                f"  Summary: {summary_path}",
            ],
            True,
        )

    def packet_status_lines(self) -> list[str]:
        packet_path = getattr(self, "packet_file", self.proj_path / ".chatboks" / "packets.jsonl")
        if not packet_path.exists():
            return ["- Thought packets: none captured yet."]
        try:
            records = packet_records_from_jsonl(packet_path.read_text(encoding="utf-8-sig"))
        except OSError as exc:
            return [f"- Thought packets: WARN, could not read {packet_path}: {exc}"]
        if not records:
            return [f"- Thought packets: none parseable in {packet_path}"]
        latest = records[-1]
        packet = latest.get("packet") if isinstance(latest, dict) else {}
        packet = packet if isinstance(packet, dict) else {}
        agent = packet.get("agent") or latest.get("sender") or "unknown"
        stance = packet.get("stance") or "UNKNOWN"
        signal = packet.get("signal") or "UNKNOWN"
        observed = packet.get("observed") if isinstance(packet.get("observed"), list) else []
        risks = packet.get("risks") if isinstance(packet.get("risks"), list) else []
        lines = [
            f"- Thought packets: {len(records)} captured",
            f"  Latest: {agent} {stance} -> {signal}; observed {len(observed)}, risks {len(risks)}",
        ]
        next_action = str(packet.get("next_action") or "").strip()
        if next_action:
            lines.append(f"  Next action: {next_action}")
        return lines

    def resume_session_lines(self) -> list[str]:
        main_agents = ", ".join(self.proj_config.get("agents", [])) or "none"
        direct_agents = sorted(self.proj_config.get("direct_agents", {}) or {})
        direct_text = ", ".join(direct_agents) if direct_agents else "none"
        counts = self.state.get("context", {}).get("token_counts", {})
        token_total = sum(int(value or 0) for value in counts.values()) if isinstance(counts, dict) else 0
        return [
            f"- Session: {self.state.get('status', 'unknown')}; next agent {self.state.get('next_agent', 'you')}",
            f"  Mode: {self.state.get('collaboration_mode', 'default')}; context {self.state.get('context_mode', 'lean')}",
            f"  Agents: {main_agents}; direct: {direct_text}",
            f"  Session tokens: {token_total:,}",
        ]

    def resume_next_action_lines(self, graphify_lines: list[str], has_sleep_memory: bool) -> list[str]:
        if self.source_worktree_dirty():
            action = "Review or commit the current working tree before broad changes."
        elif any("Freshness: STALE" in line or "Freshness: WARN" in line for line in graphify_lines):
            action = "Refresh Graphify with `graphify update . && graphify tree --label ChatBoks`."
        elif not has_sleep_memory:
            action = "Run /sleep when you pause this work block to create durable session memory."
        else:
            action = "Ready for work."
        return [
            f"- Next action: {action}",
            "  Full diagnostics: python doctor.py <project>",
        ]

    def handle_graph_command(self) -> None:
        lines = ["Graph status:"]
        lines.extend(self.codegraph_status_lines())
        lines.extend(self.graphify_status_lines())
        self.stream.system("\n".join(lines))

    def codegraph_status_lines(self) -> list[str]:
        db_path = self.context.find_codegraph_db(self.config.get("context", {}).get("codegraph", {}))
        if not db_path:
            return ["- CodeGraph: WARN, database not found. Run `codegraph init -i` or `codegraph sync`."]
        conn = None
        try:
            import sqlite3

            conn = sqlite3.connect(db_path)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {}
            for table in ("files", "nodes", "edges"):
                if table in tables:
                    counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error as exc:
            return [f"- CodeGraph: FAIL, SQLite query failed for {db_path}: {exc}"]
        finally:
            if conn is not None:
                conn.close()
        detail = []
        for label, key in (("files", "files"), ("nodes", "nodes"), ("edges", "edges")):
            if key in counts:
                detail.append(f"{counts[key]} {label}")
        suffix = f" ({', '.join(detail)})" if detail else ""
        return [f"- CodeGraph: OK{suffix}", f"  DB: {db_path}"]

    def graphify_status_lines(self) -> list[str]:
        graph_dir = self.proj_path / "graphify-out"
        graph_path = graph_dir / "graph.json"
        report_path = graph_dir / "GRAPH_REPORT.md"
        tree_path = graph_dir / "GRAPH_TREE.html"
        if not graph_dir.exists():
            return ["- Graphify: WARN, graphify-out not found. Run `graphify update .`."]
        lines = [f"- Graphify graph: {graph_path if graph_path.exists() else 'missing'}"]
        if tree_path.exists():
            lines.append(f"  Tree: {tree_path}")
        if not report_path.exists():
            lines.append(f"  Freshness: WARN, missing {report_path}")
            return lines
        report = self.read_graphify_report(report_path)
        built_commit = self.parse_graphify_built_commit(report)
        summary = self.parse_graphify_summary(report)
        source_commit = self.latest_source_commit()
        if summary:
            lines.append(f"  Summary: {summary}")
        if self.source_worktree_dirty():
            lines.append("  Freshness: WARN, source working tree has uncommitted non-graphify changes")
            return lines
        if not built_commit:
            lines.append("  Freshness: WARN, no built commit found in GRAPH_REPORT.md")
            return lines
        if not source_commit:
            lines.append(f"  Freshness: WARN, built from {self.short_commit(built_commit)}, source commit unavailable")
            return lines
        if self.commits_match(built_commit, source_commit):
            lines.append(f"  Freshness: OK, built from latest source commit {self.short_commit(source_commit)}")
        else:
            lines.append(
                "  Freshness: STALE, "
                f"built from {self.short_commit(built_commit)}, latest source commit is {self.short_commit(source_commit)}"
            )
            lines.append("  Refresh: graphify update . && graphify tree --label ChatBoks")
        return lines

    @staticmethod
    def read_graphify_report(report_path: Path) -> str:
        try:
            return report_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def parse_graphify_built_commit(report: str) -> str | None:
        match = re.search(r"Built from commit:\s*`?([0-9a-fA-F]{7,40})`?", report)
        return match.group(1) if match else None

    @staticmethod
    def parse_graphify_summary(report: str) -> str | None:
        for line in report.splitlines():
            stripped = line.strip()
            if re.match(r"^-\s+\d+\s+nodes\s+.", stripped):
                return stripped.lstrip("- ").strip()
        return None

    def latest_source_commit(self) -> str | None:
        result = self.run_git(
            [
                "rev-list",
                "-1",
                "HEAD",
                "--",
                ".",
                ":(exclude)graphify-out/**",
            ]
        )
        if result.returncode != 0:
            return None
        commit = (result.stdout or "").strip().splitlines()
        return commit[0] if commit else None

    def source_worktree_dirty(self) -> bool:
        result = self.run_git(
            [
                "status",
                "--porcelain",
                "--",
                ".",
                ":(exclude)graphify-out/**",
            ]
        )
        if result.returncode != 0:
            return False
        return bool((result.stdout or "").strip())

    def run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.proj_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=utf8_env(),
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))

    @staticmethod
    def commits_match(a: str, b: str) -> bool:
        a_lower = a.lower()
        b_lower = b.lower()
        return a_lower.startswith(b_lower) or b_lower.startswith(a_lower)

    @staticmethod
    def short_commit(commit: str) -> str:
        return commit[:8]

    def handle_skills_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            skills = self.available_skills()
            if not skills:
                self.stream.system("No native ChatBoks skills found.")
                return
            lines = ["Native ChatBoks skills:"]
            lines.extend(f"- {name}: {summary}" for name, summary in skills)
            lines.append("Use /skills <name> to preview a skill.")
            self.stream.system("\n".join(lines))
            return

        requested = parts[1].strip().lower().removesuffix(".md")
        path = SKILLS_DIR / f"{requested}.md"
        try:
            resolved = path.resolve()
            skills_root = SKILLS_DIR.resolve()
        except OSError:
            self.stream.system(f"Skill not found: {requested}")
            return
        if skills_root not in resolved.parents or not resolved.is_file():
            self.stream.system(f"Skill not found: {requested}")
            return
        content = resolved.read_text(encoding="utf-8-sig")
        preview = "\n".join(content.splitlines()[:80]).strip()
        self.stream.system(preview or f"Skill is empty: {requested}")

    @staticmethod
    def available_skills() -> list[tuple[str, str]]:
        if not SKILLS_DIR.exists():
            return []
        skills: list[tuple[str, str]] = []
        for path in sorted(SKILLS_DIR.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            content = path.read_text(encoding="utf-8-sig")
            summary = Chatboks.skill_summary(content)
            skills.append((path.stem, summary))
        return skills

    @staticmethod
    def skill_summary(content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("summary:"):
                return stripped.split(":", 1)[1].strip()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped[:96]
        return "No summary provided."

    def handle_dismiss_command(self) -> None:
        proposal = self.state.get("proposal")
        if not proposal:
            self.stream.system("No active proposal to dismiss.")
            return
        proposal_id = proposal.get("id", "unknown")
        self.update_state({"proposal": None, "status": "idle", "next_agent": "you"})
        self.append_message("system", f"Proposal {proposal_id} dismissed.")

    def handle_agent_command(self, text: str) -> None:
        parts = text.split(maxsplit=3)
        if len(parts) == 1:
            self.show_agent_statuses()
            return

        agent = parts[1].lower()
        if agent not in self.config.get("agents", {}):
            known = ", ".join(sorted(self.config.get("agents", {})))
            self.stream.system(f"Unknown agent '{agent}'. Known agents: {known}")
            return

        if len(parts) == 2:
            self.show_agent_statuses(agent)
            return

        status = parts[2].lower()
        if status in {"awake", "wake", "ready"}:
            status = "available"
        if status not in AGENT_STATUSES:
            statuses = ", ".join(sorted(AGENT_STATUSES))
            self.stream.system(f"Unknown status '{status}'. Use one of: {statuses}")
            return

        detail = parts[3] if len(parts) > 3 else ""
        exhausted_until = self.parse_status_until(detail) if status == "exhausted" else None
        reason = detail if not exhausted_until else ""
        statuses = self.load_agent_statuses()
        statuses[agent] = {
            "status": status,
            "updated_at": self.timestamp(),
            "reason": reason,
        }
        if exhausted_until:
            statuses[agent]["exhausted_until"] = exhausted_until
        if status == "available":
            statuses[agent].pop("exhausted_until", None)
            statuses[agent].pop("reason", None)
        self.save_agent_statuses(statuses)
        self.update_state({"agent_status": statuses})
        self.append_message("system", f"Agent status: {agent} is {status}.")

    def show_agent_statuses(self, agent: str | None = None) -> None:
        statuses = self.load_agent_statuses()
        self.update_state({"agent_status": statuses})
        names = [agent] if agent else sorted(self.config.get("agents", {}))
        lines = ["Agent availability:"]
        for name in names:
            record = statuses.get(name, {"status": "available"})
            until_value = self.status_until_value(record)
            until = f" until {self.format_status_until(until_value)}" if until_value else ""
            remaining = f" ({self.format_remaining_until(until_value)} remaining)" if until_value else ""
            reason = f" ({record['reason']})" if record.get("reason") else ""
            lines.append(f"- {name}: {record.get('status', 'available')}{until}{remaining}{reason}")
        self.stream.system("\n".join(lines))

    @staticmethod
    def parse_status_until(detail: str) -> str | None:
        return Chatboks.parse_status_until_at(detail, datetime.now().astimezone())

    @staticmethod
    def parse_status_until_at(detail: str, now: datetime) -> str | None:
        if not detail:
            return None
        value = detail.strip().lower()
        if value.startswith("until "):
            value = value.removeprefix("until ").strip()
        if value.endswith("m") and value[:-1].isdigit():
            return (now + timedelta(minutes=int(value[:-1]))).isoformat(timespec="seconds")
        if value.endswith("h") and value[:-1].isdigit():
            return (now + timedelta(hours=int(value[:-1]))).isoformat(timespec="seconds")
        hour_text, sep, minute_text = value.partition(":")
        if sep and hour_text.isdigit() and minute_text.isdigit():
            hour = int(hour_text)
            minute = int(minute_text)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                return target.isoformat(timespec="seconds")
        return None

    def resolve_available_agents(self, agents: list[str], exclusive_agent: str | None) -> list[str]:
        statuses = self.load_agent_statuses()
        self.update_state({"agent_status": statuses})
        if exclusive_agent:
            if self.agent_is_available(exclusive_agent, statuses):
                return agents
            self.stream.system(
                f"{exclusive_agent} is exhausted or unavailable. "
                f"Use /agent {exclusive_agent} available to retry, or address another agent."
            )
            return []

        resolved: list[str] = []
        substitutions: list[str] = []
        for agent in agents:
            if self.agent_is_available(agent, statuses):
                if agent not in resolved:
                    resolved.append(agent)
                continue
            fallback = self.find_agent_fallback(agent, statuses, resolved)
            if fallback:
                if fallback not in resolved:
                    resolved.append(fallback)
                message = f"Agent availability: substituting {fallback} for exhausted {agent}."
                self.append_message("system", message)
                substitutions.append(f"{agent} -> {fallback}")
            else:
                substitutions.append(f"{agent} skipped")

        if substitutions:
            self.stream.system("Agent availability: " + "; ".join(substitutions))
        if not resolved:
            self.stream.system("No available agents for this round. Update /agent status or route explicitly.")
        return resolved

    def find_agent_fallback(
        self,
        agent: str,
        statuses: dict[str, dict[str, Any]],
        already_selected: list[str],
    ) -> str | None:
        configured = self.config.get("agent_fallbacks", {})
        candidates = configured.get(agent, DEFAULT_AGENT_FALLBACKS.get(agent, []))
        configured_agents = self.config.get("agents", {})
        record = statuses.get(agent) or {}
        if str(record.get("status", "available")).lower() != "exhausted":
            return None
        for candidate, can_fill_main_seat in self.normalize_fallback_candidates(candidates):
            if candidate in already_selected:
                continue
            if candidate not in configured_agents:
                continue
            if not can_fill_main_seat and not self.fallback_can_fill_main_seat(candidate):
                continue
            if self.agent_is_available(candidate, statuses):
                return candidate
        return None

    def normalize_fallback_candidates(self, candidates: Any) -> list[tuple[str, bool]]:
        if isinstance(candidates, dict):
            candidates = candidates.get("candidates", [])
        if not isinstance(candidates, list):
            return []
        normalized: list[tuple[str, bool]] = []
        for item in candidates:
            if isinstance(item, str):
                normalized.append((item, False))
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("agent") or "").strip()
                if name:
                    normalized.append((name, bool(item.get("can_fill_main_seat"))))
        return normalized

    def fallback_can_fill_main_seat(self, agent: str) -> bool:
        agent_config = self.config.get("agents", {}).get(agent, {})
        if "can_fill_main_seat" in agent_config:
            return bool(agent_config.get("can_fill_main_seat"))
        return agent in self.proj_config.get("agents", [])

    @staticmethod
    def agent_is_available(agent: str, statuses: dict[str, dict[str, Any]]) -> bool:
        record = statuses.get(agent) or {}
        status = str(record.get("status", "available")).lower()
        expiry = Chatboks.parse_status_datetime(Chatboks.status_until_value(record))
        if expiry and datetime.now().astimezone() >= expiry:
            return True
        return status in {"available", "low"}

    def load_agent_statuses(self) -> dict[str, dict[str, Any]]:
        path = self.agent_status_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        now = datetime.now().astimezone()
        changed = False
        for agent, record in list(data.items()):
            if not isinstance(record, dict):
                data.pop(agent, None)
                changed = True
                continue
            expiry = self.parse_status_datetime(self.status_until_value(record))
            if expiry and now >= expiry:
                data[agent] = {
                    "status": "available",
                    "updated_at": self.timestamp(),
                }
                changed = True
        if changed:
            self.save_agent_statuses(data)
        return data

    def save_agent_statuses(self, statuses: dict[str, dict[str, Any]]) -> None:
        self.ensure_project_files()
        self.agent_status_path().write_text(
            json.dumps(statuses, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def agent_status_path(self) -> Path:
        return self.state_file.parent / "agent_status.json"

    @staticmethod
    def format_status_until(until: Any) -> str:
        expiry = Chatboks.parse_status_datetime(until)
        if expiry:
            return expiry.strftime("%Y-%m-%d %H:%M:%S")
        return str(until)

    @staticmethod
    def format_remaining_until(until: Any) -> str:
        expiry = Chatboks.parse_status_datetime(until)
        if not expiry:
            return "unknown"
        seconds = max(0, int((expiry - datetime.now().astimezone()).total_seconds()))
        hours, remainder = divmod(seconds, 3600)
        minutes = (remainder + 59) // 60
        if hours and minutes:
            return f"{hours}h {minutes}m"
        if hours:
            return f"{hours}h"
        return f"{max(1, minutes)}m"

    @staticmethod
    def status_until_value(record: dict[str, Any]) -> Any:
        return record.get("exhausted_until") or record.get("until")

    @staticmethod
    def parse_status_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)) or str(value).strip().replace(".", "", 1).isdigit():
                return datetime.fromtimestamp(float(value)).astimezone()
        except (TypeError, ValueError, OSError):
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.astimezone()

    def handle_mode_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        if len(parts) == 1 or parts[1].strip().lower() in {"list", "show", "status"}:
            current = self.state.get("collaboration_mode", "default")
            modes = ", ".join(sorted(COLLABORATION_MODES))
            self.stream.system(f"Current mode: {current}\nAvailable modes: {modes}")
            return

        mode = parts[1].strip().lower()
        if mode in {"reset", "standard"}:
            mode = "default"
        if mode not in COLLABORATION_MODES:
            modes = ", ".join(sorted(COLLABORATION_MODES))
            self.stream.system(f"Unknown mode '{mode}'. Available modes: {modes}")
            return

        self.update_state(
            {
                "collaboration_mode": mode,
                "collaboration_mode_instruction": COLLABORATION_MODES[mode],
            }
        )
        self.append_message("system", f"Collaboration mode set to {mode}.")

    def handle_context_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        if len(parts) == 1 or parts[1].strip().lower() in {"show", "status"}:
            current = self.state.get("context_mode", "lean")
            self.stream.system("Current context mode: " + current + "\nAvailable modes: lean, normal, full")
            return

        mode = parts[1].strip().lower()
        if mode not in {"lean", "normal", "full"}:
            self.stream.system("Unknown context mode. Use one of: lean, normal, full")
            return
        self.update_state({"context_mode": mode})
        self.append_message("system", f"Context mode set to {mode}.")

    def handle_sleep_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        command = parts[0].lower() if parts else "/sleep"
        action = parts[1].strip().lower() if len(parts) > 1 else ("status" if command == "/memory" else "run")
        if action in {"status", "show", "latest"}:
            self.show_sleep_status()
            return
        if action not in {"run", "now"}:
            self.stream.system("Unknown /sleep option. Try /sleep or /sleep status.")
            return

        summary = self.context.summarize(self.chatboks_md)
        record = self.write_sleep_memory(summary)
        self.append_summary_checkpoint("chatboks", "manual sleep consolidation", summary)
        self.update_state(
            {
                "last_sleep": {
                    "timestamp": record["timestamp"],
                    "summary_path": record["summary_path"],
                    "items": record["items"],
                }
            }
        )
        self.stream.system("\n".join(self.sleep_closure_lines(record)))

    def sleep_closure_lines(self, record: dict[str, Any]) -> list[str]:
        lines = [
            "Sleep complete. Work block closed.",
            "- Memory: consolidated transcript into durable session memory",
            f"  Items preserved: {record['items']}",
            f"  Summary: {record['summary_path']}",
            f"  Metadata: {record['metadata_path']}",
        ]
        lines.extend(self.codegraph_sync_closure_lines())
        lines.extend(self.graphify_sleep_closure_lines())
        lines.extend(self.git_sleep_closure_lines())
        lines.append("- Full diagnostics: python doctor.py <project>")
        lines.append("- Wake command: /resume")
        return lines

    def codegraph_sync_closure_lines(self) -> list[str]:
        if shutil.which("codegraph") is None:
            return ["- CodeGraph sync: SKIP, `codegraph` not found on PATH"]
        try:
            result = subprocess.run(
                ["codegraph", "sync"],
                cwd=self.proj_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=utf8_env(),
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [f"- CodeGraph sync: WARN, {exc}"]
        if result.returncode != 0:
            detail = self.truncate_for_state((result.stderr or result.stdout or "sync failed").strip(), 300)
            return [f"- CodeGraph sync: WARN, {detail}"]
        lines = ["- CodeGraph sync: OK"]
        lines.extend(f"  {line}" for line in self.codegraph_status_lines())
        return lines

    def graphify_sleep_closure_lines(self) -> list[str]:
        lines = self.graphify_status_lines()
        if any("STALE" in line or "WARN" in line for line in lines):
            lines.append("  Sleep note: refresh Graphify after source/doc changes are committed.")
        return lines

    def git_sleep_closure_lines(self) -> list[str]:
        return self.resume_git_lines()

    def show_sleep_status(self) -> None:
        latest = self.sleep_latest_path()
        if not latest.exists():
            self.stream.system("No sleep memory yet. Run /sleep to consolidate this session.")
            return
        text = latest.read_text(encoding="utf-8-sig").strip()
        if not text:
            self.stream.system("Sleep memory exists but is empty. Run /sleep to refresh it.")
            return
        self.stream.system(text)

    def handle_outcome_command(self, text: str) -> None:
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            self.stream.system(f"Could not parse outcome command: {exc}")
            return

        if not parts:
            return

        command = parts[0].lower()
        if command == "/outcome":
            if len(parts) < 6:
                self.stream.system(
                    'Usage: /outcome <win|failure> <agent> <category> <impact> "note"'
                )
                return
            outcome_type, agent, category, impact = parts[1:5]
            note = " ".join(parts[5:])
        else:
            if len(parts) < 5:
                self.stream.system(
                    f'Usage: {command} <agent> <category> <impact> "note"'
                )
                return
            outcome_type = "win" if command == "/win" else "failure"
            agent, category, impact = parts[1:4]
            note = " ".join(parts[4:])

        outcome_type = outcome_type.lower()
        if outcome_type not in {"win", "failure"}:
            self.stream.system("Outcome type must be 'win' or 'failure'.")
            return
        if not note.strip():
            self.stream.system("Outcome note cannot be empty.")
            return

        record = {
            "timestamp": self.timestamp(),
            "project": self.project,
            "round": int(self.state.get("round", 0)),
            "type": outcome_type,
            "agent": agent.lower(),
            "category": category.lower(),
            "impact": impact.lower(),
            "mode": "manual",
            "note": note.strip(),
        }
        self.append_outcome(record)
        self.append_message(
            "system",
            (
                f"Outcome recorded: {record['type']} / {record['agent']} / "
                f"{record['category']} / {record['impact']}."
            ),
        )

    def handle_usage_command(self, text: str) -> None:
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            self.stream.system(f"Could not parse usage command: {exc}")
            return

        if len(parts) == 1 or parts[1].lower() in {"show", "status"}:
            self.show_usage_baselines()
            return

        action = parts[1].lower()
        if action != "sync":
            self.stream.system("Usage: /usage | /usage sync <anthropic|openai|google|all>")
            return

        if len(parts) < 3:
            self.stream.system("Usage: /usage sync <anthropic|openai|google|all>")
            return

        target = parts[2].lower()
        if target == "all":
            for provider in USAGE_PROVIDERS:
                self.sync_usage_provider(provider)
            return

        self.sync_usage_provider(target)

    def show_usage_baselines(self, provider: str | None = None, limit: int = 6) -> None:
        records = self.load_usage_baselines()
        if provider:
            records = [record for record in records if record.get("provider") == provider]
        if not records:
            providers = ", ".join(sorted(USAGE_PROVIDERS))
            self.stream.system(
                "No usage baselines saved yet.\n"
                f"Available providers: {providers}\n"
                "Run /usage sync <provider> to capture one."
            )
            return

        recent = records[-limit:]
        latest_by_provider: dict[str, dict[str, Any]] = {}
        for record in records:
            provider_name = str(record.get("provider", "unknown"))
            latest_by_provider[provider_name] = record

        lines = [
            f"Usage baselines: {len(records)}",
            "Latest by provider:",
        ]
        for provider_name in sorted(latest_by_provider):
            record = latest_by_provider[provider_name]
            if record.get("status") == "error":
                status = f"error: {record.get('error') or 'sync failed'}"
            else:
                status = "login required" if record.get("login_required") else "ready"
            highlights = ", ".join(record.get("highlights") or []) or "no usage highlights detected"
            lines.append(
                f"- {provider_name}: {status} @ {record.get('timestamp')} | {highlights}"
            )

        lines.append("Recent captures:")
        for record in recent:
            if record.get("status") == "error":
                summary = f"error: {record.get('error') or 'sync failed'}"
            else:
                summary = ", ".join(record.get("highlights") or []) or "no usage highlights detected"
            lines.append(
                f"- {record.get('provider')} {record.get('timestamp')} "
                f"({record.get('title') or 'untitled'}): "
                f"{summary}"
            )
        self.stream.system("\n".join(lines))

    def handle_latency_command(self, text: str = "/latency") -> None:
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            self.stream.system(f"Could not parse latency command: {exc}")
            return

        limit = 10
        if len(parts) > 1:
            try:
                limit = max(1, min(50, int(parts[1])))
            except ValueError:
                self.stream.system("Usage: /latency [recent-count]")
                return

        records = self.load_cli_latency_records(limit=limit)
        if not records:
            self.stream.system(
                "No CLI latency records yet.\n"
                "Run a real agent turn, then try /latency again."
            )
            return

        self.stream.system("\n".join(self.format_cli_latency_lines(records)))

    def load_cli_latency_records(self, limit: int | None = None) -> list[dict[str, Any]]:
        path = self.cli_latency_path()
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(data)
        return records[-limit:] if limit else records

    def cli_latency_path(self) -> Path:
        return self.state_file.parent / "cli_latency.jsonl"

    @classmethod
    def format_cli_latency_lines(cls, records: list[dict[str, Any]]) -> list[str]:
        lines = [f"CLI latency: {len(records)} recent call{'s' if len(records) != 1 else ''}"]
        for record in records:
            agent = record.get("agent") or "unknown"
            mode = record.get("mode") or "?"
            profile = record.get("adapter_profile") or "profile?"
            timestamp = record.get("timestamp") or "timestamp?"
            timeout_reason = record.get("timeout_reason")
            timeout_suffix = f" timeout={timeout_reason}" if timeout_reason else ""
            stdout_chars = cls.latency_count(record, "stdout_chars", "stdout_bytes")
            stderr_chars = cls.latency_count(record, "stderr_chars", "stderr_bytes")
            lines.append(
                f"- {timestamp} {agent}/{mode} profile={profile} "
                f"total={cls.format_latency_seconds(cls.latency_value(record, 'total_seconds', 'duration_seconds'))} "
                f"spawn={cls.format_latency_seconds(cls.latency_value(record, 'spawn_seconds'))} "
                f"first_output={cls.format_latency_seconds(cls.latency_value(record, 'first_output_seconds', 'first_stdout_seconds'))} "
                f"first_stdout={cls.format_latency_seconds(cls.latency_value(record, 'first_stdout_seconds'))} "
                f"runtime={cls.format_latency_seconds(cls.latency_value(record, 'runtime_seconds', 'process_runtime_seconds'))} "
                f"out={cls.format_compact_number(stdout_chars)}c err={cls.format_compact_number(stderr_chars)}c"
                f"{timeout_suffix}"
            )

        averages = cls.average_latency_fields(records)
        if averages:
            lines.append(
                "Averages: "
                f"total={cls.format_latency_seconds(averages.get('total'))} "
                f"spawn={cls.format_latency_seconds(averages.get('spawn_seconds'))} "
                f"first_output={cls.format_latency_seconds(averages.get('first_output'))} "
                f"first_stdout={cls.format_latency_seconds(averages.get('first_stdout_seconds'))} "
                f"runtime={cls.format_latency_seconds(averages.get('runtime'))}"
            )
        noisy = cls.stderr_heavy_latency_records(records)
        if noisy:
            lines.append(
                "Stderr-heavy runs: "
                + "; ".join(
                    (
                        f"{record.get('agent') or 'unknown'} "
                        f"err={cls.format_compact_number(cls.latency_count(record, 'stderr_chars', 'stderr_bytes'))}c "
                        f"total={cls.format_latency_seconds(cls.latency_value(record, 'total_seconds', 'duration_seconds'))}"
                    )
                    for record in noisy[:3]
                )
            )
        return lines

    @classmethod
    def average_latency_fields(cls, records: list[dict[str, Any]]) -> dict[str, float]:
        averages: dict[str, float] = {}
        fields = {
            "total": ("total_seconds", "duration_seconds"),
            "spawn_seconds": ("spawn_seconds",),
            "first_output": ("first_output_seconds", "first_stdout_seconds"),
            "first_stdout_seconds": ("first_stdout_seconds",),
            "runtime": ("runtime_seconds", "process_runtime_seconds"),
        }
        for label, aliases in fields.items():
            values = [
                float(value)
                for record in records
                if isinstance((value := cls.latency_value(record, *aliases)), (int, float))
            ]
            if values:
                averages[label] = sum(values) / len(values)
        return averages

    @staticmethod
    def latency_value(record: dict[str, Any], *fields: str) -> float | int | None:
        for field in fields:
            value = record.get(field)
            if isinstance(value, (int, float)):
                return value
        return None

    @classmethod
    def latency_count(cls, record: dict[str, Any], *fields: str) -> int:
        value = cls.latency_value(record, *fields)
        if value is None:
            return 0
        return max(0, int(value))

    @classmethod
    def stderr_heavy_latency_records(
        cls,
        records: list[dict[str, Any]],
        threshold_chars: int = 50_000,
    ) -> list[dict[str, Any]]:
        noisy = [
            record
            for record in records
            if cls.latency_count(record, "stderr_chars", "stderr_bytes") >= threshold_chars
        ]
        return sorted(
            noisy,
            key=lambda record: cls.latency_count(record, "stderr_chars", "stderr_bytes"),
            reverse=True,
        )

    @staticmethod
    def format_latency_seconds(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "-"
        return f"{value:.3f}s"

    def sync_usage_provider(self, provider: str) -> dict[str, Any] | None:
        provider_config = self.resolve_usage_provider(provider)
        if provider_config is None:
            known = ", ".join(sorted(USAGE_PROVIDERS))
            self.stream.system(f"Unknown usage provider '{provider}'. Known providers: {known}")
            return None

        label = str(provider_config.get("label") or provider.title())
        self.stream.system(f"Syncing usage baseline for {label}...")
        record = self.capture_usage_baseline(provider, provider_config)
        self.append_usage_baseline(record)

        if record.get("status") == "ok":
            summary = ", ".join(record.get("highlights") or []) or "no usage highlights detected"
            state = "login required" if record.get("login_required") else "usage page detected"
            self.stream.system(
                f"Usage baseline saved for {provider}: {state}. {summary}"
            )
        else:
            self.stream.system(
                f"Usage baseline sync failed for {provider}: {record.get('error') or 'unknown error'}"
            )
        return record

    def resolve_usage_provider(self, provider: str) -> dict[str, Any] | None:
        built_in = USAGE_PROVIDERS.get(provider)
        overrides = self.config.get("usage_providers", {})
        custom = overrides.get(provider) if isinstance(overrides, dict) else None
        if not built_in and not custom:
            return None
        resolved = dict(built_in or {})
        if isinstance(custom, dict):
            resolved.update(custom)
        return resolved

    def capture_usage_baseline(self, provider: str, provider_config: dict[str, Any]) -> dict[str, Any]:
        timestamp = self.timestamp()
        artifact_dir = self.usage_artifact_dir(provider, timestamp)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        url = str(provider_config.get("url") or "")

        try:
            self.run_playwright_cli(["open", url], artifact_dir, provider)
            self.run_playwright_cli(
                ["run-code", "await page.waitForLoadState('domcontentloaded'); await page.waitForTimeout(1500)"],
                artifact_dir,
                provider,
            )
            final_url = self.run_playwright_cli_value(["eval", "location.href"], artifact_dir, provider)
            title = self.run_playwright_cli_value(["eval", "document.title"], artifact_dir, provider)
            body_text = self.run_playwright_cli_value(
                ["eval", "() => document.body ? document.body.innerText.slice(0, 4000) : ''"],
                artifact_dir,
                provider,
            )
            screenshot_output = self.run_playwright_cli(["screenshot"], artifact_dir, provider)
            screenshot_path = self.detect_playwright_screenshot(artifact_dir, screenshot_output)
        except RuntimeError as exc:
            return {
                "timestamp": timestamp,
                "project": self.project,
                "provider": provider,
                "label": str(provider_config.get("label") or provider.title()),
                "url_requested": url,
                "status": "error",
                "error": str(exc),
                "artifact_dir": str(artifact_dir),
            }
        finally:
            self.close_playwright_usage_session(artifact_dir, provider)

        login_required = self.usage_login_required(final_url, title, body_text)
        highlights = self.extract_usage_highlights(body_text)
        return {
            "timestamp": timestamp,
            "project": self.project,
            "provider": provider,
            "label": str(provider_config.get("label") or provider.title()),
            "url_requested": url,
            "final_url": final_url.strip(),
            "title": title.strip(),
            "status": "ok",
            "login_required": login_required,
            "highlights": highlights,
            "body_excerpt": body_text.strip()[:2000],
            "artifact_dir": str(artifact_dir),
            "screenshot_path": str(screenshot_path) if screenshot_path else None,
        }

    def run_playwright_cli(
        self,
        args: list[str],
        artifact_dir: Path,
        provider: str,
        timeout: int = 120,
    ) -> str:
        npx_cmd = shutil.which("npx.cmd") or shutil.which("npx")
        if not npx_cmd:
            raise RuntimeError("npx.cmd was not found on PATH. Install Node.js/npm first.")

        command = [
            npx_cmd,
            "--yes",
            "--package",
            "@playwright/cli",
            "playwright-cli",
            "--session",
            f"chatboks-usage-{provider}",
            *args,
        ]
        result = subprocess.run(
            command,
            cwd=artifact_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_env(),
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        if result.returncode != 0:
            raise RuntimeError(error or output or f"Playwright CLI failed: {' '.join(args)}")
        return output

    def run_playwright_cli_value(
        self,
        args: list[str],
        artifact_dir: Path,
        provider: str,
        timeout: int = 120,
    ) -> str:
        output = self.run_playwright_cli(["--raw", *args], artifact_dir, provider, timeout=timeout)
        return self.extract_playwright_value(output)

    def close_playwright_usage_session(self, artifact_dir: Path, provider: str) -> None:
        try:
            self.run_playwright_cli(["close"], artifact_dir, provider, timeout=30)
        except RuntimeError:
            return

    def append_usage_baseline(self, record: dict[str, Any]) -> None:
        self.ensure_project_files()
        path = self.usage_baselines_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_usage_baselines(self) -> list[dict[str, Any]]:
        path = self.usage_baselines_path()
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(data)
        return records

    def usage_baselines_path(self) -> Path:
        return self.state_file.parent / "usage_baselines.jsonl"

    def usage_artifact_dir(self, provider: str, timestamp: str) -> Path:
        safe_timestamp = timestamp.replace(":", "-")
        return self.proj_path / "output" / "playwright" / "usage" / provider / safe_timestamp

    @staticmethod
    def usage_login_required(final_url: str, title: str, body_text: str) -> bool:
        combined = " ".join([final_url.lower(), title.lower(), body_text.lower()])
        markers = (
            "sign in",
            "log in",
            "login",
            "continue with google",
            "continue with openai",
            "continue with anthropic",
            "enter your password",
            "verify it",
            "authentication required",
        )
        return any(marker in combined for marker in markers)

    @staticmethod
    def extract_usage_highlights(body_text: str, limit: int = 8) -> list[str]:
        keywords = ("usage", "spend", "cost", "credit", "quota", "limit", "token", "api")
        highlights: list[str] = []
        for raw_line in body_text.splitlines():
            line = " ".join(raw_line.split()).strip()
            lowered = line.lower()
            if not line or len(line) < 3:
                continue
            if any(keyword in lowered for keyword in keywords):
                highlights.append(line[:180])
            if len(highlights) >= limit:
                break
        return highlights

    @staticmethod
    def detect_playwright_screenshot(artifact_dir: Path, command_output: str) -> Path | None:
        for line in command_output.splitlines():
            candidate = line.strip().strip('"')
            if candidate.lower().endswith(".png"):
                path = Path(candidate)
                if not path.is_absolute():
                    path = artifact_dir / path
                if path.exists():
                    return path
        screenshots = sorted(artifact_dir.glob("*.png"), key=lambda path: path.stat().st_mtime)
        return screenshots[-1] if screenshots else None

    @staticmethod
    def extract_playwright_value(output: str) -> str:
        stripped = output.strip()
        if stripped.startswith("### Result"):
            lines = [line.strip() for line in stripped.splitlines() if line.strip()]
            for line in lines:
                if line.startswith("### Result "):
                    value = line.removeprefix("### Result ").strip()
                    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                        return value[1:-1]
                    return value
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
            return stripped[1:-1]
        return stripped

    def handle_outcome_suggestion_command(self, text: str) -> None:
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            self.stream.system(f"Could not parse outcome suggestion command: {exc}")
            return

        if not parts:
            return

        agent_filter = parts[1].lower() if len(parts) > 1 else None
        if agent_filter and agent_filter not in self.config.get("agents", {}):
            known = ", ".join(sorted(self.config.get("agents", {})))
            self.stream.system(
                f"Unknown agent '{agent_filter}'. Known agents: {known}"
            )
            return

        prompt = self.build_outcome_suggestion_prompt(agent_filter)
        self.stream.system("Asking Coordinator for outcome suggestions...")
        response = self.call_coordinator_direct(prompt)
        if response is None:
            return
        body = self.strip_signal_suffix(response)
        if not body:
            body = "Coordinator returned no outcome suggestions."
        self.stream.system(body)

    def build_outcome_suggestion_prompt(self, agent_filter: str | None = None) -> str:
        recent_chat = self.load_recent_transcript_lines(limit=18)
        if agent_filter:
            filtered_chat = [
                line for line in recent_chat
                if f"[{agent_filter.upper()}]" in line.upper() or line.startswith("[YOU]") or line.startswith("[SYSTEM]")
            ]
            if filtered_chat:
                recent_chat = filtered_chat

        recent_outcomes = self.load_outcomes()[-6:]
        outcome_lines = [
            (
                f"- {record.get('type')} {record.get('agent')} "
                f"{record.get('category')} {record.get('impact')}: {record.get('note')}"
            )
            for record in recent_outcomes
        ] or ["- No prior outcomes recorded."]

        target = agent_filter or "any agent"
        return "\n".join(
            [
                "Suggest collaboration outcome scoring commands for ChatBoks.",
                "Return up to 3 candidate commands, one per line, each starting with /win or /fail.",
                "After each command, add one short plain-text explanation line.",
                "Do not record anything automatically. Do not use markdown fences.",
                "If there is not enough signal, say so briefly and end with >>> TASK_COMPLETE.",
                "",
                f"Target agent filter: {target}",
                f"Current round: {int(self.state.get('round', 0))}",
                f"Current collaboration mode: {self.state.get('collaboration_mode', 'default')}",
                "",
                "[RECENT TRANSCRIPT]",
                *recent_chat,
                "",
                "[RECENT OUTCOMES]",
                *outcome_lines,
            ]
        )

    def append_outcome(self, record: dict[str, Any]) -> None:
        self.ensure_project_files()
        path = self.outcomes_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def show_outcomes(self, outcome_type: str | None = None, limit: int = 8) -> None:
        records = self.load_outcomes()
        if outcome_type:
            records = [record for record in records if record.get("type") == outcome_type]
        if not records:
            label = outcome_type + "s" if outcome_type else "outcomes"
            self.stream.system(f"No {label} recorded yet.")
            return

        total = len(records)
        by_agent: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for record in records:
            by_agent[str(record.get("agent", "?"))] = by_agent.get(str(record.get("agent", "?")), 0) + 1
            by_category[str(record.get("category", "?"))] = by_category.get(str(record.get("category", "?")), 0) + 1

        recent = records[-limit:]
        lines = [
            f"Outcomes: {total}",
            "By agent: " + self.format_counts(by_agent),
            "By category: " + self.format_counts(by_category),
            "Recent:",
        ]
        lines.extend(
            (
                f"- {record.get('type')} {record.get('agent')} "
                f"{record.get('category')} {record.get('impact')}: {record.get('note')}"
            )
            for record in recent
        )
        self.stream.system("\n".join(lines))

    def load_outcomes(self) -> list[dict[str, Any]]:
        path = self.outcomes_path()
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(data)
        return records

    def outcomes_path(self) -> Path:
        return self.state_file.parent / "outcomes.jsonl"

    def load_recent_transcript_lines(self, limit: int = 12) -> list[str]:
        self.ensure_project_files()
        lines = [
            line.rstrip()
            for line in self.chatboks_md.read_text(encoding="utf-8-sig").splitlines()
            if line.startswith("[")
        ]
        return lines[-limit:] if limit > 0 else lines

    def call_coordinator_direct(self, prompt: str) -> str | None:
        if "coordinator" not in self.config.get("agents", {}):
            self.stream.system("Coordinator is not configured for this ChatBoks install.")
            return None

        statuses = self.load_agent_statuses()
        self.update_state({"agent_status": statuses})
        if not self.agent_is_available("coordinator", statuses):
            self.stream.system(
                "Coordinator is exhausted or unavailable. Use /agent coordinator available when it is ready again."
            )
            return None

        try:
            self.check_token_limit("coordinator")
            agent = self.router.get_agent("coordinator")
            response = agent.call(prompt)
        except AgentTimeoutError as exc:
            self.stream.system(f"Coordinator timed out while suggesting outcomes: {exc}")
            return None
        except TokenExhaustionError as exc:
            self.stream.system(f"Coordinator hit its token limit while suggesting outcomes: {exc}")
            return None

        self.update_token_count("coordinator", response)
        return response

    def strip_signal_suffix(self, response: str) -> str:
        signal = self.parse_signal(response)
        if not signal:
            return response.strip()
        before_signal, _, _ = response.rpartition(f">>> {signal}")
        return before_signal.strip()

    @staticmethod
    def format_counts(counts: dict[str, int]) -> str:
        return ", ".join(
            f"{key}={value}" for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        )

    def handle_external_update(self) -> None:
        if self._internal_write:
            return
        self.state = self.load_state()
        if self.state.get("status") == "handoff":
            self.stream.system("External handoff detected.")
            self.handle_handoff()

    def handle_commit_trigger(self) -> None:
        self.state = self.load_state()
        if self.state.get("status") == "handoff":
            self.handle_handoff()
        else:
            self.stream.system("Commit trigger received, but no handoff is pending.")

    def handle_handoff(self) -> None:
        handoff_to = self.state.get("handoff_to") or self.router.primary()
        if handoff_to not in self.proj_config["agents"]:
            self.stream.system(f"Handoff target '{handoff_to}' is not configured; using primary.")
            handoff_to = self.router.primary()
        self.update_state({"status": "active", "next_agent": handoff_to})
        self.run_agent_round(agents=[handoff_to])

    def max_handoff_depth(self) -> int:
        raw_depth = self.config.get("rounds", {}).get("max_handoff_depth")
        if raw_depth is None:
            return 3
        return max(1, int(raw_depth))

    def select_handoff_target(self, agent_name: str) -> str:
        after = self.router.after(agent_name)
        if after and after != "you" and after != agent_name and after in self.proj_config["agents"]:
            return after
        for candidate in self.proj_config.get("agents") or []:
            if candidate != agent_name:
                return candidate
        return self.router.primary()

    def prepare_handoff(
        self,
        response: str,
        agent_name: str,
        *,
        target: str | None = None,
        status: str = "handoff",
    ) -> bool:
        handoff_to = target or self.select_handoff_target(agent_name)
        depth = int(self.state.get("handoff_depth", 0) or 0) + 1
        max_depth = self.max_handoff_depth()
        updates = {
            "handoff_depth": depth,
            "handoff_to": handoff_to,
            "handoff_reason": self.extract_first_line(response),
            "handoff_context": response,
            "next_agent": handoff_to,
        }
        if depth >= max_depth:
            self.update_state(
                {
                    **updates,
                    "status": "blocked",
                    "next_agent": "you",
                    "blocked_reason": "handoff_deadlock",
                }
            )
            self.stream.system(
                f"Handoff deadlock: depth {depth} reached without completion. Your input needed."
            )
            return False
        self.update_state({**updates, "status": status})
        self.stream.system(f"Handoff queued for {handoff_to} (depth {depth}/{max_depth}).")
        return True

    def confirmation_mode_active(self, intent: str) -> bool:
        if intent == "confirm":
            return False
        return str(self.state.get("collaboration_mode") or "default").lower() == "confirmation"

    def confirmation_repair_budget(self) -> int:
        raw_budget = self.config.get("rounds", {}).get("max_confirmation_repairs")
        if raw_budget is None:
            return 1
        return max(0, int(raw_budget))

    def select_confirmation_agent(self, executor: str, active_agents: list[str]) -> str | None:
        statuses = self.load_agent_statuses()
        self.update_state({"agent_status": statuses})
        candidates: list[str] = []
        for agent in list(self.proj_config.get("agents") or []):
            if agent != executor and agent not in candidates:
                candidates.append(agent)
        for agent in active_agents:
            if agent != executor and agent not in candidates:
                candidates.append(agent)
        for agent in candidates:
            if self.agent_is_available(agent, statuses):
                return agent
        return None

    def confirmation_request_text(
        self,
        executor: str,
        verifier: str,
        initiator: str | None,
        executor_response: str,
    ) -> str:
        task = initiator or self.state.get("active_task") or "the current task"
        lines = [
            "Confirmation mode:",
            f"- Responsible agent: {executor}",
            f"- Verifier: {verifier}",
            f"- Original request: {task}",
            "",
            "Verifier instructions:",
            "- Do not redo the task or duplicate implementation work.",
            "- Check whether the responsible agent's claimed outcome is complete, tested, and consistent with the request.",
            "- If the executor supplied a Thought Packet, use its observed facts and risks as your checklist.",
            "- Address each actionable packet risk explicitly before replying >>> TASK_COMPLETE.",
            "- Reply >>> TASK_COMPLETE only if the outcome is confirmed.",
            "- Reply >>> HANDOFF with specific missing work if the responsible agent should repair it.",
            "- Reply >>> BLOCKED only if human input or external state is required.",
        ]
        packet_lines = self.confirmation_packet_checklist_lines(executor_response, executor)
        if packet_lines:
            lines.extend(["", *packet_lines])
        lines.extend(
            [
                "",
                "Responsible agent output under review:",
                self.strip_signal_suffix(executor_response),
            ]
        )
        return "\n".join(lines)

    def confirmation_packet_checklist_lines(self, executor_response: str, executor: str) -> list[str]:
        packets = extract_packets(executor_response, fallback_agent=executor)
        if not packets:
            return []
        packet = packets[-1]
        lines = ["Executor Thought Packet checklist:"]
        if packet.observed:
            lines.append("- Observed facts:")
            lines.extend(f"  - {item}" for item in packet.observed)
        risks = self.actionable_packet_risks(packet.risks)
        if risks:
            lines.append("- Actionable risks to resolve or explicitly accept:")
            lines.extend(f"  - {item}" for item in risks)
        elif packet.risks:
            lines.append("- Packet risks: none actionable.")
        if packet.next_action:
            lines.append(f"- Packet next action: {packet.next_action}")
        lines.append(f"- Packet signal: {packet.signal}")
        return lines

    def actionable_packet_risks(self, risks: list[str]) -> list[str]:
        ignored = {
            "none",
            "no risk",
            "no risks",
            "no known risk",
            "no known risks",
            "no remaining risk",
            "no remaining risks",
            "n/a",
            "na",
        }
        actionable: list[str] = []
        for risk in risks:
            normalized = " ".join(str(risk or "").strip().lower().split())
            if not normalized or normalized in ignored:
                continue
            actionable.append(risk)
        return actionable

    def unresolved_packet_risks(self, executor_response: str, verifier_response: str, executor: str) -> list[str]:
        packets = extract_packets(executor_response, fallback_agent=executor)
        if not packets:
            return []
        risks = self.actionable_packet_risks(packets[-1].risks)
        if not risks:
            return []
        if self.verifier_addresses_packet_risks(verifier_response, risks):
            return []
        return risks

    def verifier_addresses_packet_risks(self, verifier_response: str, risks: list[str]) -> bool:
        text = verifier_response.lower()
        anchors = [anchor for risk in risks if (anchor := self.risk_anchor(risk))]
        if "risk" not in text and "risks" not in text and not any(anchor in text for anchor in anchors):
            return False
        resolution_words = (
            "addressed",
            "acknowledge",
            "acknowledged",
            "accepted",
            "confirmed",
            "mitigated",
            "resolved",
            "reviewed",
        )
        negative_words = ("remaining", "unresolved")
        strong_resolution_words = tuple(word for word in resolution_words if word != "confirmed")
        if (
            any(re.search(rf"\b{re.escape(word)}\b", text) for word in negative_words)
            and not any(re.search(rf"\b{re.escape(word)}\b", text) for word in strong_resolution_words)
        ):
            return False
        if any(re.search(rf"\b{re.escape(word)}\b", text) for word in resolution_words):
            return True
        return False

    def risk_anchor(self, risk: str) -> str:
        words = [word.strip(".,:;()[]{}\"'`").lower() for word in risk.split()]
        words = [word for word in words if len(word) >= 4]
        return " ".join(words[:4])

    def confirm_completion_if_needed(
        self,
        executor: str,
        executor_response: str,
        initiator: str | None,
        active_agents: list[str],
        intent: str,
    ) -> str | None:
        if not self.confirmation_mode_active(intent):
            return None
        verifier = self.select_confirmation_agent(executor, active_agents)
        if verifier is None:
            self.append_message("system", "Confirmation mode: no available verifier; accepting completion.")
            return "confirmed"

        request = self.confirmation_request_text(executor, verifier, initiator, executor_response)
        self.append_message("system", request)
        self.update_state(
            {
                "status": "active",
                "round_intent": "confirm",
                "expected_agents": [verifier],
                "completed_agents": [],
                "next_agent": verifier,
                "active_task": request,
                "confirmation": {
                    "executor": executor,
                    "verifier": verifier,
                    "repairs_used": int(self.state.get("confirmation_repairs_used", 0) or 0),
                },
            }
        )

        response = self.call_agent_with_token_recovery(verifier, mode="respond")
        signal = self.parse_signal(response)
        self.append_message(verifier, response)
        self.update_token_count(verifier, response)
        self.mark_agent_completed(verifier)
        self.update_state({"last_agent": verifier, "next_agent": "you"})

        unresolved_risks = self.unresolved_packet_risks(executor_response, response, executor)
        if signal in {"TASK_COMPLETE", "TASK COMPLETE", "SKIP"} and unresolved_risks:
            risk_lines = "\n".join(f"- {risk}" for risk in unresolved_risks)
            verifier_gap = "\n".join(
                [
                    "Verifier returned completion without addressing actionable executor packet risks.",
                    "The responsible agent must resolve or explicitly retire these risks:",
                    risk_lines,
                    ">>> HANDOFF",
                ]
            )
            self.append_message("system", verifier_gap)
            return self.handle_confirmation_repair(executor, verifier, verifier_gap, initiator)
        if signal in {"TASK_COMPLETE", "TASK COMPLETE", "SKIP"}:
            self.stream.system(f"Confirmation complete: {verifier} verified {executor}'s output.")
            return "confirmed"
        if signal == "QUESTION":
            self.handle_question(response)
            return "terminal"
        return self.handle_confirmation_repair(executor, verifier, response, initiator)

    def handle_confirmation_repair(
        self,
        executor: str,
        verifier: str,
        verifier_response: str,
        initiator: str | None,
    ) -> str:
        repairs_used = int(self.state.get("confirmation_repairs_used", 0) or 0)
        if repairs_used >= self.confirmation_repair_budget():
            self.stream.system("Confirmation blocked: repair budget exhausted. Your input needed.")
            self.update_state(
                {
                    "status": "blocked",
                    "next_agent": "you",
                    "confirmation": {
                        "executor": executor,
                        "verifier": verifier,
                        "repairs_used": repairs_used,
                        "blocked_reason": "repair_budget_exhausted",
                    },
                }
            )
            return "terminal"

        repairs_used += 1
        self.update_state({"confirmation_repairs_used": repairs_used})
        repair_request = "\n".join(
            [
                "Confirmation repair:",
                f"{verifier} did not confirm {executor}'s output.",
                "Address only the verifier's concrete objections, preserve partial work, then end with a control signal.",
                "",
                "Verifier response:",
                self.strip_signal_suffix(verifier_response),
            ]
        )
        self.append_message("system", repair_request)
        self.stream.system(f"Confirmation requested repair from {executor}; returning control to {executor}.")
        self.update_state(
            {
                "status": "active",
                "next_agent": executor,
                "active_task": repair_request,
                "confirmation": {
                    "executor": executor,
                    "verifier": verifier,
                    "repairs_used": repairs_used,
                },
            }
        )
        self.run_agent_round(initiator=repair_request, agents=[executor], intent="confirmation_repair")
        return "terminal"

    def run_agent_round(
        self,
        initiator: str | None = None,
        agents: list[str] | None = None,
        intent: str = "respond",
    ) -> None:
        active_agents = agents or list(self.proj_config["agents"])
        max_rounds = int(self.config.get("rounds", {}).get("max_before_escalate", 3))

        for _ in range(max_rounds):
            pending_proposal: tuple[str, str] | None = None
            completed_agent: str | None = None
            self.state["round"] = int(self.state.get("round", 0)) + 1
            self.state["round_intent"] = intent
            self.state["expected_agents"] = active_agents
            self.state["completed_agents"] = []
            self.save_state()

            for index, agent_name in enumerate(active_agents):
                is_last_agent = index == len(active_agents) - 1
                next_agent = "you" if is_last_agent else active_agents[index + 1]
                response = self.call_agent_with_token_recovery(agent_name, mode="respond")
                signal = self.parse_signal(response)

                if signal == "SKIP":
                    self.update_token_count(agent_name, response)
                    self.mark_agent_completed(agent_name)
                    self.append_message(
                        "system",
                        f"{agent_name} skipped: no materially different input.",
                    )
                    self.update_state({"last_agent": agent_name, "next_agent": next_agent})
                    continue

                self.append_message(agent_name, response)
                self.update_token_count(agent_name, response)
                self.mark_agent_completed(agent_name)
                self.update_state({"last_agent": agent_name, "next_agent": next_agent})

                if signal == "PROPOSAL":
                    if pending_proposal is None:
                        pending_proposal = (response, agent_name)
                    continue
                if signal == "QUESTION":
                    self.handle_question(response)
                    return
                if signal == "HANDOFF":
                    if not is_last_agent:
                        if not self.prepare_handoff(response, agent_name, target=next_agent, status="active"):
                            return
                        continue
                    confirmation = self.confirm_completion_if_needed(agent_name, response, initiator, active_agents, intent)
                    if confirmation == "confirmed":
                        self.maybe_announce_direct_standby_agents(initiator, active_agents)
                        self.stream.system("Task complete. Awaiting next instruction.")
                        self.update_state({"status": "idle", "active_task": None, "confirmation": None})
                        self.update_state({"handoff_depth": 0})
                        return
                    if confirmation == "terminal":
                        return
                    self.handle_agent_handoff(response, agent_name)
                    return
                if signal in {"TASK_COMPLETE", "TASK COMPLETE"}:
                    completed_agent = agent_name
                    if not is_last_agent:
                        continue
                    confirmation = self.confirm_completion_if_needed(agent_name, response, initiator, active_agents, intent)
                    if confirmation == "confirmed":
                        self.maybe_announce_direct_standby_agents(initiator, active_agents)
                        self.stream.system("Task complete. Awaiting next instruction.")
                        self.update_state({"status": "idle", "active_task": None, "confirmation": None})
                        self.update_state({"handoff_depth": 0})
                        return
                    if confirmation == "terminal":
                        return
                    self.maybe_announce_direct_standby_agents(initiator, active_agents)
                    self.stream.system("Task complete. Awaiting next instruction.")
                    self.update_state({"status": "idle", "active_task": None, "confirmation": None})
                    self.update_state({"handoff_depth": 0})
                    return
                if signal == "BLOCKED":
                    if completed_agent is not None:
                        self.stream.system(
                            f"{agent_name} blocked after {completed_agent} completed the task; treating as a warning."
                        )
                        if not is_last_agent:
                            continue
                        self.maybe_announce_direct_standby_agents(initiator, active_agents)
                        self.stream.system("Task complete. Awaiting next instruction.")
                        self.update_state({"status": "idle", "active_task": None, "confirmation": None})
                        self.update_state({"handoff_depth": 0})
                        return
                    if not is_last_agent:
                        self.stream.system(f"{agent_name} blocked. Continuing to {next_agent}.")
                        continue
                    self.stream.system("Agent blocked. Your input needed.")
                    self.update_state({"status": "blocked", "next_agent": "you"})
                    return

            if pending_proposal:
                self.handle_proposal(*pending_proposal)
                return

            if self.all_expected_agents_completed():
                self.maybe_announce_direct_standby_agents(initiator, active_agents)
                self.stream.system("Round complete. Awaiting next instruction.")
                self.update_state({"status": "idle", "next_agent": "you"})
                return

        self.stream.escalate("Agents have not reached consensus. Your call.")
        self.update_state({"status": "awaiting_approval", "next_agent": "you"})

    def parse_signal(self, response: str) -> str | None:
        upper = response.upper()
        last_pos = -1
        last_signal = None
        for signal in SIGNALS:
            pos = upper.rfind(f">>> {signal}")
            if pos > last_pos:
                last_pos = pos
                last_signal = signal
        return last_signal

    def maybe_announce_direct_standby_agents(
        self,
        initiator: str | None,
        active_agents: list[str],
    ) -> None:
        if not self.is_role_call_request(initiator):
            return
        standby_agents = self.direct_standby_agents(active_agents)
        if not standby_agents:
            return
        for agent_name in standby_agents:
            self.stream.standby(agent_name, self.format_direct_standby_message(agent_name))

    def direct_standby_agents(self, active_agents: list[str]) -> list[str]:
        configured = self.proj_config.get("direct_agents", [])
        return [
            name
            for name in configured
            if name in self.config.get("agents", {}) and name not in active_agents
        ]

    @staticmethod
    def is_role_call_request(text: str | None) -> bool:
        if not text:
            return False
        normalized = " ".join(text.strip().lower().split())
        return normalized in ROLE_CALL_REQUESTS

    def format_direct_standby_message(self, agent_name: str) -> str:
        alias = DIRECT_AGENT_ALIASES.get(agent_name, f"@{agent_name}")
        return (
            f"Standby via {alias}. Available on demand; stays idle unless explicitly routed "
            "or needed as a fallback."
        )

    def handle_proposal(self, response: str, proposed_by: str) -> None:
        proposal = {
            "id": f"prop_{int(time.time())}",
            "summary": self.extract_first_line(response),
            "raw": response,
            "proposed_by": proposed_by,
            "endorsed_by": [],
            "challenged_by": [],
        }
        self.update_state(
            {
                "status": "awaiting_approval",
                "next_agent": "you",
                "proposal": proposal,
            }
        )
        estimate = self.estimate_execution_cost()
        proposal["execution_estimate"] = estimate
        self.stream.proposal(self.format_proposal_gate(proposal, estimate))
        self.stream.system("Type APPROVE, MODIFY, or REJECT.")

    def handle_question(self, response: str) -> None:
        self.update_state({"status": "awaiting_input", "next_agent": "you"})
        self.stream.system("Question raised. Your input is needed.")

    def handle_agent_handoff(self, response: str, agent_name: str) -> None:
        if self.prepare_handoff(response, agent_name):
            self.handle_handoff()

    def handle_approval(self, text: str) -> None:
        verdict = text.strip().upper()

        if verdict in {"APPROVE", "YES", "Y", "OK", "GO"}:
            self.stream.system("Approved. Executing...")
            self.update_state({"status": "executing", "next_agent": self.router.primary()})
            self.execute_proposal()
        elif verdict == "REJECT":
            self.stream.system("Rejected. Agents notified.")
            self.append_message("you", "Proposal rejected. Please revise.")
            self.update_state({"status": "active", "proposal": None})
            self.run_agent_round()
        else:
            modification = self.normalize_modification(text)
            self.append_message("system", f"Modification requested: {modification}")
            self.update_state(
                {
                    "status": "active",
                    "round_intent": "revise",
                    "active_task": f"Revise the current proposal using this modification: {modification}",
                }
            )
            self.run_agent_round(initiator=modification, intent="revise")

    def execute_proposal(self) -> None:
        if not self.ensure_session_token_budget():
            self.update_state({"status": "blocked", "next_agent": "you"})
            return
        lead = self.router.primary()
        agents = self.resolve_available_agents([lead], exclusive_agent=None)
        if not agents:
            self.update_state({"status": "blocked", "next_agent": "you"})
            return
        lead = agents[0]
        response = self.call_agent_with_token_recovery(lead, mode="execute")
        self.append_message(lead, response)
        signal = self.parse_signal(response)
        self.update_state(
            {
                "status": "idle" if signal != "BLOCKED" else "blocked",
                "proposal": None,
            }
        )

    def estimate_execution_cost(self) -> dict[str, Any]:
        lead = self.estimate_execution_target()
        if not lead:
            return {
                "agent": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_usd": None,
                "cost_configured": False,
                "note": "No available execution agent.",
            }

        context_pkg = self.context.build(self.state, self.chatboks_md)
        agent = self.router.get_agent(lead)
        prompt = agent.build_prompt(context_pkg, mode="execute")
        input_tokens = self.estimate_token_count(prompt)
        output_tokens = self.estimate_execution_output_tokens(lead, input_tokens)
        input_cost = self.estimate_token_cost(lead, "cost_per_million_input_tokens", input_tokens)
        output_cost = self.estimate_token_cost(lead, "cost_per_million_output_tokens", output_tokens)
        total_cost = None
        if input_cost is not None and output_cost is not None:
            total_cost = input_cost + output_cost
        return {
            "agent": lead,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_usd": input_cost,
            "output_usd": output_cost,
            "total_usd": total_cost,
            "cost_configured": total_cost is not None,
        }

    def estimate_execution_target(self) -> str | None:
        lead = self.router.primary()
        statuses = self.load_agent_statuses()
        if self.agent_is_available(lead, statuses):
            return lead
        return self.find_agent_fallback(lead, statuses, []) or None

    def estimate_execution_output_tokens(self, agent_name: str, input_tokens: int) -> int:
        agent_config = self.config.get("agents", {}).get(agent_name, {})
        configured = agent_config.get("estimated_execute_output_tokens")
        if configured is not None:
            return max(1, int(configured))
        return max(750, min(6000, input_tokens // 3 if input_tokens else 1500))

    def estimate_token_cost(
        self,
        agent_name: str,
        field: str,
        token_count: int,
    ) -> float | None:
        agent_config = self.config.get("agents", {}).get(agent_name, {})
        rate = agent_config.get(field)
        if rate is None:
            return None
        return (float(rate) * max(0, token_count)) / 1_000_000.0

    @staticmethod
    def estimate_token_count(text: str) -> int:
        return max(1, len(text) // 4)

    def format_proposal_gate(self, proposal: dict[str, Any], estimate: dict[str, Any]) -> str:
        lines = [f"Proposal from {proposal.get('proposed_by')}:", proposal.get("summary") or "No summary."]
        agent = estimate.get("agent")
        if agent:
            lines.append(
                "Estimated execution via "
                f"{agent}: ~{self.format_compact_number(int(estimate.get('input_tokens', 0)))} input "
                f"+ ~{self.format_compact_number(int(estimate.get('output_tokens', 0)))} output tokens."
            )
        if estimate.get("cost_configured"):
            lines.append(
                "Estimated cost: "
                f"{self.format_usd(float(estimate.get('total_usd', 0.0)))} "
                f"({self.format_usd(float(estimate.get('input_usd', 0.0)))} in, "
                f"{self.format_usd(float(estimate.get('output_usd', 0.0)))} out)."
            )
        elif agent:
            lines.append(
                "Estimated cost: unavailable until "
                f"{agent} has cost_per_million_input_tokens and cost_per_million_output_tokens configured."
            )
        if estimate.get("note"):
            lines.append(str(estimate["note"]))
        return "\n".join(lines)

    @staticmethod
    def format_usd(value: float) -> str:
        return f"${value:.4f}"

    @staticmethod
    def format_compact_number(value: int) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}m"
        if value >= 10_000:
            return f"{value // 1_000}k"
        if value >= 1_000:
            return f"{value / 1_000:.1f}k"
        return str(value)

    def call_agent_with_token_recovery(self, agent_name: str, mode: str) -> str:
        context_config = self.config.get("context", {})
        retries = int(context_config.get("max_token_recovery_retries", 2))
        timeout_retries = int(context_config.get("max_timeout_recovery_retries", 1))
        agent = self.router.get_agent(agent_name)
        timeout_attempts = 0
        timeout_diff_snapshots: list[str] = []
        token_attempt = 0

        while token_attempt <= retries:
            self.check_token_limit(agent_name)
            activity_started_at = time.monotonic()
            self.stream.agent_activity_start(agent_name, mode)
            streamed_output_parts: list[str] = []
            previous_stdout_callback = getattr(agent, "stdout_callback", None)

            def stream_stdout_chunk(chunk: str) -> None:
                if not streamed_output_parts:
                    self.stream.agent_output_start(agent_name, mode)
                streamed_output_parts.append(chunk)
                self.stream.agent_output_delta(agent_name, chunk)

            if hasattr(agent, "stdout_callback"):
                agent.stdout_callback = stream_stdout_chunk
            try:
                context_pkg = self.context.build(self.state, self.chatboks_md)
                if mode == "execute":
                    response = agent.execute(context_pkg)
                else:
                    response = agent.call(context_pkg)
                if streamed_output_parts and response.strip() == "".join(streamed_output_parts).strip():
                    if not hasattr(self, "_streamed_agent_responses"):
                        self._streamed_agent_responses = {}
                    self._streamed_agent_responses[agent_name.lower()] = response.strip()
                return response
            except AgentTimeoutError as exc:
                timeout_attempts += 1
                current_diff = self.capture_git_diff()
                if self.agent_timeout_is_looping(current_diff, timeout_diff_snapshots):
                    return self.loop_recovery_blocked(agent_name, exc, timeout_attempts)
                if current_diff.strip():
                    timeout_diff_snapshots.append(current_diff)
                if not self.recover_agent_timeout(
                    agent_name,
                    exc,
                    timeout_attempts,
                    timeout_retries,
                ):
                    return self.timeout_recovery_blocked(agent_name, exc, timeout_attempts)
            except TokenExhaustionError as exc:
                if token_attempt >= retries:
                    return self.token_recovery_blocked(agent_name, str(exc), retries)
                token_attempt += 1
                if not self.recover_token_exhaustion(
                    agent_name,
                    str(exc),
                    token_attempt,
                    retries,
                ):
                    return self.token_recovery_blocked(agent_name, str(exc), token_attempt)
            finally:
                if hasattr(agent, "stdout_callback"):
                    agent.stdout_callback = previous_stdout_callback
                self.stream.agent_output_finish(agent_name)
                self.stream.agent_activity_finish(
                    agent_name,
                    mode,
                    time.monotonic() - activity_started_at,
                )

        return self.token_recovery_blocked(agent_name, "Retry budget exhausted.", retries)

    def check_token_limit(self, agent_name: str) -> None:
        agent_config = self.config["agents"][agent_name]
        current = self.state["context"]["token_counts"].get(agent_name, 0)
        warning = int(agent_config.get("token_warning", 100_000))

        if current >= warning:
            self.recover_token_exhaustion(
                agent_name,
                f"Estimated token count {current} reached warning threshold {warning}.",
                attempt=0,
                max_retries=0,
            )

    def session_token_budget(self) -> dict[str, int]:
        context_config = self.config.get("context", {})
        counts = self.state.get("context", {}).setdefault("token_counts", {})
        return {
            "used": self.total_session_tokens(),
            "warning": int(context_config.get("session_token_budget_warning", 0) or 0),
            "limit": int(context_config.get("session_token_budget_limit", 0) or 0),
            "agent_count": len(counts),
        }

    def total_session_tokens(self) -> int:
        counts = self.state.get("context", {}).setdefault("token_counts", {})
        return sum(int(value or 0) for value in counts.values())

    def ensure_session_token_budget(self) -> bool:
        budget = self.session_token_budget()
        used = budget["used"]
        warning = budget["warning"]
        limit = budget["limit"]
        context_state = self.state.get("context", {})

        if warning > 0 and used < warning:
            context_state["session_budget_warning_emitted"] = False
        if limit > 0 and used < limit:
            context_state["session_budget_limit_emitted"] = False

        if warning > 0 and used >= warning and not context_state.get("session_budget_warning_emitted"):
            message = (
                f"Session token warning: estimated usage is {used} / {warning} warning "
                f"({limit} hard cap)." if limit > 0 else
                f"Session token warning: estimated usage is {used} / {warning} warning."
            )
            self.stream.system(message)
            self.append_message("system", message)
            context_state["session_budget_warning_emitted"] = True
            self.save_state()

        if limit > 0 and used >= limit:
            if not context_state.get("session_budget_limit_emitted"):
                message = (
                    f"Session token cap reached: estimated usage is {used} / {limit}. "
                    "New work is blocked until context is reduced."
                )
                self.stream.system(message)
                self.append_message("system", message)
                context_state["session_budget_limit_emitted"] = True
                self.save_state()
            self.update_state({"status": "blocked", "next_agent": "you"})
            return False
        return True

    def recover_token_exhaustion(
        self,
        agent_name: str,
        reason: str,
        attempt: int,
        max_retries: int,
    ) -> bool:
        retry_text = (
            f" Recovery retry {attempt}/{max_retries}."
            if max_retries
            else " Proactive context reset."
        )
        self.stream.system(
            f"{agent_name} token context exhausted. Compressing transcript.{retry_text}"
        )
        summary = self.context.summarize(self.chatboks_md)
        self.append_summary_checkpoint(agent_name, reason, summary)
        agent = self.router.get_agent(agent_name)
        codegraph = self.context.load_codegraph()
        try:
            resume_response = agent.reinitialize(codegraph, summary, self.state)
        except TokenExhaustionError as exc:
            self.stream.system(
                f"{agent_name} could not reload compressed context: "
                f"{self.truncate_for_state(str(exc))}"
            )
            return False

        if agent.is_token_exhaustion(resume_response):
            self.stream.system(f"{agent_name} still reports token exhaustion after compression.")
            return False

        self.append_message(
            "system",
            f"{agent_name} reinitialized after context compression. Retrying with compact context.",
        )
        self.state["context"]["token_counts"][agent_name] = 0
        self.save_state()
        self.refresh_token_usage_display()
        return True

    def append_summary_checkpoint(self, agent_name: str, reason: str, summary: str) -> None:
        self.append_message(
            "system",
            "\n".join(
                [
                    ">>> SUMMARY_CHECKPOINT",
                    f"Agent: {agent_name}",
                    f"Reason: {self.truncate_for_state(reason)}",
                    summary,
                    ">>> SUMMARY_CHECKPOINT_END",
                ]
            ),
        )

    def write_sleep_memory(self, summary: str) -> dict[str, Any]:
        timestamp = self.timestamp()
        safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("T", "-")
        sleep_dir = self.sleep_dir()
        sleep_dir.mkdir(parents=True, exist_ok=True)

        items = self.summary_item_count(summary)
        summary_text = "\n".join(
            [
                "[SLEEP MEMORY - READ-ONLY CONSOLIDATED CONTEXT]",
                f"Project: {self.project}",
                f"Timestamp: {timestamp}",
                "Purpose: durable offline consolidation for future agent context.",
                "",
                summary.strip() or "[SUMMARY] No decision lines found.",
                "",
                "Instructions: Treat this as prior context, not as a new user request.",
            ]
        )

        latest_path = sleep_dir / "latest.md"
        archive_path = sleep_dir / f"{safe_timestamp}.md"
        metadata_path = sleep_dir / "latest.json"
        history_path = sleep_dir / "history.jsonl"
        record = {
            "project": self.project,
            "timestamp": timestamp,
            "items": items,
            "summary_path": str(latest_path),
            "archive_path": str(archive_path),
            "metadata_path": str(metadata_path),
            "source": str(self.chatboks_md),
        }

        latest_path.write_text(summary_text + "\n", encoding="utf-8")
        archive_path.write_text(summary_text + "\n", encoding="utf-8")
        metadata_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return record

    def sleep_dir(self) -> Path:
        return self.proj_path / ".chatboks" / "sleep"

    def sleep_latest_path(self) -> Path:
        return self.sleep_dir() / "latest.md"

    @staticmethod
    def summary_item_count(summary: str) -> int:
        return sum(1 for line in summary.splitlines() if line.strip().startswith("- "))

    def capture_git_diff(self) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "--no-ext-diff", "--"],
                cwd=self.proj_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=utf8_env(),
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout

    def agent_timeout_is_looping(self, current_diff: str, previous_diffs: list[str]) -> bool:
        current_lines = self.diff_changed_lines(current_diff)
        if not current_lines:
            return False
        threshold = float(self.config.get("context", {}).get("timeout_loop_overlap_threshold", 0.8))
        for previous_diff in previous_diffs:
            previous_lines = self.diff_changed_lines(previous_diff)
            if not previous_lines:
                continue
            overlap = len(current_lines & previous_lines) / len(current_lines)
            if overlap >= threshold:
                return True
        return False

    @staticmethod
    def diff_changed_lines(diff: str) -> set[str]:
        changed: set[str] = set()
        for line in diff.splitlines():
            if line.startswith(("+++", "---")):
                continue
            if line.startswith(("+", "-")):
                changed.add(line)
        return changed

    def recover_agent_timeout(
        self,
        agent_name: str,
        error: AgentTimeoutError,
        attempt: int,
        max_retries: int,
    ) -> bool:
        if error.partial_output:
            self.append_message(
                "system",
                "\n".join(
                    [
                        ">>> TIMEOUT_CHECKPOINT",
                        f"Agent: {agent_name}",
                        f"Reason: {self.truncate_for_state(str(error))}",
                        "Partial output captured before timeout:",
                        self.truncate_for_state(error.partial_output, limit=2000),
                    ]
                ),
            )
        if attempt > max_retries:
            return False

        self.stream.system(
            f"{agent_name} {error.reason} timed out. "
            f"Retrying with preserved partial output ({attempt}/{max_retries})."
        )
        self.append_message(
            "system",
            "\n".join(
                [
                    ">>> TIMEOUT_RECOVERY",
                    f"Agent: {agent_name}",
                    f"Attempt: {attempt}/{max_retries}",
                    "Continue from the preserved checkpoint. Do not repeat completed work.",
                ]
            ),
        )
        return True

    def token_recovery_blocked(self, agent_name: str, reason: str, retries: int) -> str:
        return "\n".join(
            [
                f"{agent_name} hit token exhaustion and automatic recovery did not complete.",
                f"Recovery attempts: {retries}.",
                f"Last error: {self.truncate_for_state(reason)}",
                "The transcript has been summarized where possible; user input is needed before continuing.",
                ">>> BLOCKED",
            ]
        )

    def loop_recovery_blocked(
        self,
        agent_name: str,
        error: AgentTimeoutError,
        attempts: int,
    ) -> str:
        self.append_message(
            "system",
            "\n".join(
                [
                    ">>> LOOP_DETECTED",
                    f"Agent: {agent_name}",
                    f"Attempts: {attempts}",
                    f"Reason: repeated git diff after timeout recovery ({self.truncate_for_state(str(error))})",
                ]
            ),
        )
        return "\n".join(
            [
                f"{agent_name} appears to be looping during timeout recovery.",
                f"Recovery attempts: {attempts}.",
                "The latest git diff substantially matches a previous timeout attempt.",
                "Partial output and loop evidence have been checkpointed; user input is needed before continuing.",
                ">>> BLOCKED",
            ]
        )

    def timeout_recovery_blocked(
        self,
        agent_name: str,
        error: AgentTimeoutError,
        attempts: int,
    ) -> str:
        return "\n".join(
            [
                f"{agent_name} timed out and automatic recovery did not complete.",
                f"Recovery attempts: {attempts}.",
                f"Last error: {self.truncate_for_state(str(error))}",
                "Partial output has been checkpointed where available; user input is needed before continuing.",
                ">>> BLOCKED",
            ]
        )

    @staticmethod
    def truncate_for_state(text: str, limit: int = 500) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

    def update_token_count(self, agent_name: str, response: str) -> None:
        tokens = max(1, len(response) // 4)
        counts = self.state["context"].setdefault("token_counts", {})
        counts[agent_name] = counts.get(agent_name, 0) + tokens
        self.save_state()
        self.ensure_session_token_budget()
        self.refresh_token_usage_display()

    def refresh_token_usage_display(self) -> None:
        counts = self.state.get("context", {}).setdefault("token_counts", {})
        self.stream.token_usage(counts, self.session_token_budget())

    def mark_agent_completed(self, agent_name: str) -> None:
        completed = self.state.setdefault("completed_agents", [])
        if agent_name not in completed:
            completed.append(agent_name)
        self.save_state()

    def all_expected_agents_completed(self) -> bool:
        expected = set(self.state.get("expected_agents") or [])
        completed = set(self.state.get("completed_agents") or [])
        return bool(expected) and expected.issubset(completed)

    def append_message(self, sender: str, text: str) -> None:
        self.ensure_project_files()
        self.capture_thought_packets(sender, text)
        tag = self.sender_tag(sender)
        timestamp = time.strftime("%H:%M:%S")
        line = f"\n{tag} {text.strip()}\n"
        self._internal_write = True
        try:
            with self.chatboks_md.open("a", encoding="utf-8") as handle:
                handle.write(line)
        finally:
            self._internal_write = False
        if sender.lower() != "you":
            streamed_response = getattr(self, "_streamed_agent_responses", {}).pop(sender.lower(), None)
            if streamed_response != text.strip():
                self.stream.message(sender, text, timestamp)

    def capture_thought_packets(self, sender: str, text: str) -> None:
        if sender.lower() in {"you", "system"}:
            return
        packets = extract_packets(text, fallback_agent=sender)
        for packet in packets:
            self.append_thought_packet(packet, sender)

    def append_thought_packet(self, packet: ThoughtPacket, sender: str) -> None:
        packet_file = getattr(self, "packet_file", self.proj_path / ".chatboks" / "packets.jsonl")
        packet_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": self.timestamp(),
            "project": self.project,
            "sender": sender,
            "round": self.state.get("round"),
            "context": self.thought_packet_context(sender),
            "packet": self.packet_record_for_memory(packet),
        }
        with packet_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def packet_record_for_memory(self, packet: ThoughtPacket) -> dict[str, Any]:
        record = packet.to_record()
        anchored, downgraded = split_observed_by_anchor(packet.observed)
        record["observed"] = anchored
        record["evidence"] = "anchored" if anchored else "none"
        if downgraded:
            record["downgraded"] = downgraded
        return record

    def thought_packet_context(self, sender: str) -> dict[str, Any]:
        intent = str(self.state.get("round_intent") or "respond")
        mode = str(self.state.get("collaboration_mode") or "default")
        context: dict[str, Any] = {
            "intent": intent,
            "mode": mode,
        }
        active_task = self.state.get("active_task")
        if active_task:
            context["active_task"] = self.truncate_context_value(active_task)

        confirmation = self.state.get("confirmation")
        if isinstance(confirmation, dict):
            executor = str(confirmation.get("executor") or "")
            verifier = str(confirmation.get("verifier") or "")
            context["confirmation"] = {
                "executor": executor,
                "verifier": verifier,
                "repairs_used": int(confirmation.get("repairs_used", 0) or 0),
                "stage": self.confirmation_packet_stage(sender, intent, executor, verifier),
            }
        elif mode == "confirmation":
            context["confirmation"] = {
                "executor": sender,
                "verifier": "",
                "repairs_used": int(self.state.get("confirmation_repairs_used", 0) or 0),
                "stage": "executor_output",
            }
        return context

    def confirmation_packet_stage(
        self,
        sender: str,
        intent: str,
        executor: str,
        verifier: str,
    ) -> str:
        if intent == "confirm" and sender == verifier:
            return "verifier_review"
        if intent == "confirmation_repair" and sender == executor:
            return "executor_repair"
        if sender == verifier:
            return "verifier_review"
        if sender == executor:
            return "executor_output"
        return "related_agent"

    def truncate_context_value(self, value: object, limit: int = 600) -> str:
        return " ".join(str(value).strip().split())[:limit]

    def buffer_or_complete_input(self, text: str) -> str | None:
        stripped = text.strip()
        if stripped.startswith("/"):
            return stripped

        if self.input_buffer and not stripped:
            completed = " ".join(self.input_buffer).strip()
            self.input_buffer = []
            return completed

        if stripped:
            self.input_buffer.append(stripped)

        joined = " ".join(self.input_buffer).strip()
        if not joined:
            return None

        if self.is_complete_user_message(joined):
            self.input_buffer = []
            return joined

        self.stream.system("Input buffered. Finish with punctuation or press Enter on a blank line to send.")
        return None

    def ensure_project_files(self) -> None:
        self.proj_path.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.chatboks_md.exists():
            session = self.state.get("session") if hasattr(self, "state") else self.timestamp()
            agents = ", ".join(self.proj_config["agents"])
            self.chatboks_md.write_text(
                (
                    "---\n"
                    f"project: {self.project}\n"
                    f"session: {session}\n"
                    f"agents: [{agents}]\n"
                    "status: active\n"
                    "---\n"
                    "[SYSTEM] Chatboks initialized.\n"
                ),
                encoding="utf-8",
            )
        if not self.state_file.exists():
            self.save_state()

    def load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            return self.normalize_state(json.loads(self.state_file.read_text(encoding="utf-8-sig")))
        return self.default_state()

    def save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def update_state(self, updates: dict[str, Any]) -> None:
        self.state.update(updates)
        self.save_state()

    def default_state(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "session": self.timestamp(),
            "status": "initializing",
            "active_task": None,
            "last_agent": None,
            "next_agent": None,
            "round": 0,
            "round_intent": "respond",
            "context_mode": "lean",
            "expected_agents": [],
            "completed_agents": [],
            "proposal": None,
            "criteria_gate": None,
            "handoff_to": None,
            "handoff_reason": None,
            "handoff_context": None,
            "handoff_depth": 0,
            "context": {
                "codegraph_snapshot": "codegraph.db",
                "token_counts": {},
                "session_budget_warning_emitted": False,
                "session_budget_limit_emitted": False,
            },
        }

    def load_config(self, config_path: Path | None) -> dict[str, Any]:
        path = config_path or Path("~/.chatboks/config.yaml").expanduser()
        if not path.exists():
            raise SystemExit(f"Missing config file: {path}")
        return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}

    def normalize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("round_intent", "respond")
        mode = str(state.get("context_mode", "lean")).lower()
        state["context_mode"] = mode if mode in {"lean", "normal", "full"} else "lean"

        # Validate collaboration_mode and always recompute instruction from canonical table -
        # never trust what state.json says the instruction text should be.
        mode = state.get("collaboration_mode", "default")
        if mode not in COLLABORATION_MODES:
            mode = "default"
        state["collaboration_mode"] = mode
        state["collaboration_mode_instruction"] = COLLABORATION_MODES[mode]

        state.setdefault("expected_agents", [])
        state.setdefault("completed_agents", [])
        if not isinstance(state.get("criteria_gate"), dict):
            state["criteria_gate"] = None
        state.setdefault("handoff_to", None)
        state["handoff_depth"] = max(0, int(state.get("handoff_depth", 0) or 0))
        state.setdefault("help_pin", True)

        # Sanitize untrusted free-text fields that come from agent output or state.json.
        for field in ("handoff_reason", "handoff_context", "active_task"):
            val = state.get(field)
            if val is not None:
                state[field] = self.truncate_for_state(str(val), 2000)
            else:
                state.setdefault(field, None)

        state.setdefault("context", {})
        state["context"].setdefault("codegraph_snapshot", "codegraph.db")
        state["context"].setdefault("token_counts", {})
        state["context"].setdefault("session_budget_warning_emitted", False)
        state["context"].setdefault("session_budget_limit_emitted", False)
        return state

    @staticmethod
    def is_complete_user_message(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        upper = stripped.upper()
        if upper in {"APPROVE", "REJECT", "MODIFY", "EXIT", "QUIT", "BYE"}:
            return True
        if upper in {
            "YES",
            "Y",
            "NO",
            "N",
            "OK",
            "GO",
            "START",
            "PROCEED",
            "CONTINUE",
            "RUN",
            "RUN IT",
            "DO IT",
            "GO AHEAD",
        }:
            return True
        if upper.startswith("MODIFY "):
            return True
        if stripped.startswith("@") and len(stripped.split()) <= 3:
            return True
        if len(stripped.split()) <= 2:
            return True
        return stripped.endswith((".", "?", "!", ":", ";", ")", "]", "}", '"', "'"))

    @staticmethod
    def extract_first_line(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(">>>"):
                return stripped[:200]
        return "No summary provided."

    @staticmethod
    def normalize_modification(text: str) -> str:
        stripped = text.strip()
        upper = stripped.upper()
        if upper == "MODIFY":
            return "Revise the proposal based on the user's requested modification."
        if upper.startswith("MODIFY "):
            return stripped[7:].strip() or "Revise the proposal."
        return stripped

    @staticmethod
    def sender_tag(sender: str) -> str:
        normalized = sender.lower()
        if normalized == "antigravity":
            return "[ANTIGRAV]"
        return f"[{sender.upper()}]"

    @staticmethod
    def timestamp() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Chatboks orchestrator")
    parser.add_argument("project", help="Project name from ~/.chatboks/config.yaml")
    parser.add_argument("--config", type=Path, help="Alternate config.yaml path")
    parser.add_argument("--trigger", default="manual", choices=["manual", "commit"])
    parser.add_argument("--watch", action="store_true", help="Watch chatboks.md for handoffs")
    parser.add_argument("--once", action="store_true", help="Run one agent round and exit")
    args = parser.parse_args(argv)

    app = Chatboks(args.project, trigger=args.trigger, config_path=args.config)
    app.start(watch=args.watch, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
