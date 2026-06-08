#!/usr/bin/env python3
"""Chatboks orchestrator.

Runs a human-supervised relay between Claude, Codex, and Antigravity using:
- chatboks.md for the readable conversation stream
- .chatboks/state.json for machine-readable session state
"""

from __future__ import annotations

import argparse
import json
import shlex
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
from router import Router
from ui.stream import Stream


SIGNALS = [
    "PROPOSAL",
    "QUESTION",
    "HANDOFF",
    "TASK_COMPLETE",
    "TASK COMPLETE",
    "BLOCKED",
    "SKIP",
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
    "diagnose": (
        "Diagnose mode. Establish the root cause with the smallest useful probes. Recommend concrete commands "
        "or narrow fixes before broad implementation."
    ),
}

AGENT_STATUSES = {"available", "low", "exhausted", "blocked"}

DEFAULT_AGENT_FALLBACKS = {
    "claude": ["codex", "agent_zero"],
    "codex": ["claude", "agent_zero"],
    "gemini": ["claude", "codex", "agent_zero"],
    "antigravity": ["codex", "claude", "agent_zero"],
}

HELP_COMMANDS = [
    ("/help", "Show this command deck."),
    ("/skills", "List native ChatBoks workflow skills."),
    ("/skills <name>", "Preview a workflow skill without calling agents."),
    ("/context", "Show current context mode: lean, normal, or full."),
    ("/context lean|normal|full", "Set how much context agents receive. Lean is default."),
    ("/agent", "List agent availability for this project."),
    ("/agent <name> exhausted 50m", "Mark a model exhausted for a timed cooldown."),
    ("/agent <name> available", "Mark a model available again."),
    ("/mode", "Show the current collaboration mode and available modes."),
    ("/mode <name>", "Set prompt framing: default, brainstorm, bugsearch, implement, review, diagnose."),
    ("/win ...", "Record a collaboration win without calling agents."),
    ("/fail ...", "Record a collaboration failure without calling agents."),
    ("/outcomes", "Show recent wins and failures."),
    ("@claude / @codex / @zero", "Route the next prompt exclusively to one agent."),
    ("@all ...", "Opt into the full configured non-direct project team for one prompt."),
    ("APPROVE / MODIFY / REJECT", "Respond to a proposal gate."),
    ("/dismiss", "Discard the active proposal without executing it."),
    ("exit / quit / bye", "End the ChatBoks terminal session."),
]

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
        self.stream = Stream(self.config.get("agents", {}), self.proj_config["agents"])
        self.router = Router(self.config, project, self.proj_path)
        self.context = ContextBuilder(self.proj_path, self.config)
        self.state = self.normalize_state(self.load_state())
        self._internal_write = False
        self.input_buffer: list[str] = []

    def start(self, watch: bool = False, once: bool = False) -> None:
        self.ensure_project_files()
        self.stream.intro(self.project)
        if self.state.get("status") == "initializing":
            self.initialize_agents()
        self.stream.ready()

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
        self.stream.role_call(self.proj_config["agents"])
        for agent_name in self.proj_config["agents"]:
            self.stream.system(f"Initializing {agent_name}...")
            agent = self.router.get_agent(agent_name)
            response = agent.initialize(codegraph)
            self.append_message(agent_name, response)
        self.update_state({"status": "active", "next_agent": self.router.primary()})

    def run_input_loop(self) -> None:
        while True:
            try:
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

        prior_status = self.state.get("status")
        self.append_message("you", text)

        if prior_status == "awaiting_approval":
            self.handle_approval(text)
            return

        agents, routed_text, exclusive_agent = self.router.route_user_prompt(text)
        agents = self.resolve_available_agents(agents, exclusive_agent)
        if not agents:
            return
        next_agent = exclusive_agent or self.router.primary()
        if next_agent not in agents:
            next_agent = agents[0]
        self.update_state(
            {
                "status": "active",
                "next_agent": next_agent,
                "active_task": routed_text,
                "agent_status": self.load_agent_statuses(),
            }
        )
        self.run_agent_round(initiator=routed_text, agents=agents)

    def handle_local_command(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return False

        command = stripped.split(maxsplit=1)[0].lower()
        if command in {"/help", "/h", "/?"}:
            self.handle_help_command()
            return True
        if command in {"/skill", "/skills"}:
            self.handle_skills_command(stripped)
            return True
        if command in {"/win", "/fail", "/outcome"}:
            self.handle_outcome_command(stripped)
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
        if command in {"/context", "/ctx"}:
            self.handle_context_command(stripped)
            return True
        if command in {"/agent", "/agents"}:
            self.handle_agent_command(stripped)
            return True
        if command == "/dismiss":
            self.handle_dismiss_command()
            return True

        self.stream.system(
            "Unknown local command. Try /help, /skills, /context, /agent, /mode, /win, /fail, /outcome, /wins, /failures, /outcomes, or /dismiss."
        )
        return True

    def handle_help_command(self) -> None:
        if hasattr(self.stream, "help_box"):
            self.stream.help_box(HELP_COMMANDS)
            return
        lines = ["ChatBoks commands:"]
        lines.extend(f"- {command}: {description}" for command, description in HELP_COMMANDS)
        self.stream.system("\n".join(lines))

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
        content = resolved.read_text(encoding="utf-8")
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
            content = path.read_text(encoding="utf-8")
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
            data = json.loads(path.read_text(encoding="utf-8"))
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
        for line in path.read_text(encoding="utf-8").splitlines():
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
                        self.update_state(
                            {
                                "status": "active",
                                "handoff_to": next_agent,
                                "handoff_reason": self.extract_first_line(response),
                                "handoff_context": response,
                            }
                        )
                        continue
                    self.handle_agent_handoff(response, agent_name)
                    return
                if signal in {"TASK_COMPLETE", "TASK COMPLETE"}:
                    if not is_last_agent:
                        continue
                    self.stream.system("Task complete. Awaiting next instruction.")
                    self.update_state({"status": "idle"})
                    return
                if signal == "BLOCKED":
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
        self.stream.system("Type APPROVE, MODIFY, or REJECT.")

    def handle_question(self, response: str) -> None:
        self.update_state({"status": "awaiting_input", "next_agent": "you"})
        self.stream.system("Question raised. Your input is needed.")

    def handle_agent_handoff(self, response: str, agent_name: str) -> None:
        target = self.router.after(agent_name) or self.router.primary()
        self.update_state(
            {
                "status": "handoff",
                "handoff_to": target,
                "handoff_reason": self.extract_first_line(response),
                "handoff_context": response,
            }
        )
        self.stream.system(f"Handoff flagged for {target}.")

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
            context_pkg = self.context.build(self.state, self.chatboks_md)
            try:
                if mode == "execute":
                    return agent.execute(context_pkg)
                return agent.call(context_pkg)
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
        self.append_message(
            "system",
            "\n".join(
                [
                    ">>> SUMMARY_CHECKPOINT",
                    f"Agent: {agent_name}",
                    f"Reason: {self.truncate_for_state(reason)}",
                    summary,
                ]
            ),
        )
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
        return True

    def capture_git_diff(self) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "--no-ext-diff", "--"],
                cwd=self.proj_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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
            self.stream.message(sender, text, timestamp)

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
            "handoff_to": None,
            "handoff_reason": None,
            "handoff_context": None,
            "context": {
                "codegraph_snapshot": "codegraph.db",
                "token_counts": {},
            },
        }

    def load_config(self, config_path: Path | None) -> dict[str, Any]:
        path = config_path or Path("~/.chatboks/config.yaml").expanduser()
        if not path.exists():
            raise SystemExit(f"Missing config file: {path}")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

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
        state.setdefault("handoff_to", None)

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
