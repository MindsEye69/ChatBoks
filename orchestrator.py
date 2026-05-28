#!/usr/bin/env python3
"""Chatboks orchestrator.

Runs a human-supervised relay between Claude, Codex, and Antigravity using:
- chatboks.md for the readable conversation stream
- .chatboks/state.json for machine-readable session state
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from context.builder import ContextBuilder
from router import Router
from ui.stream import Stream


SIGNALS = {
    "PROPOSAL",
    "QUESTION",
    "HANDOFF",
    "TASK_COMPLETE",
    "TASK COMPLETE",
    "BLOCKED",
    "SKIP",
}


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
        prior_status = self.state.get("status")
        self.append_message("you", text)

        if prior_status == "awaiting_approval":
            self.handle_approval(text)
            return

        agents, routed_text, exclusive_agent = self.router.route_user_prompt(text)
        next_agent = exclusive_agent or self.router.primary()
        self.update_state(
            {
                "status": "active",
                "next_agent": next_agent,
                "active_task": routed_text,
            }
        )
        self.run_agent_round(initiator=routed_text, agents=agents)

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
            self.state["round"] = int(self.state.get("round", 0)) + 1
            self.state["round_intent"] = intent
            self.state["expected_agents"] = active_agents
            self.state["completed_agents"] = []
            self.save_state()

            pending_proposal: tuple[str, str] | None = None
            for index, agent_name in enumerate(active_agents):
                is_last_agent = index == len(active_agents) - 1
                next_agent = "you" if is_last_agent else active_agents[index + 1]
                self.check_token_limit(agent_name)
                context_pkg = self.context.build(self.state, self.chatboks_md)
                agent = self.router.get_agent(agent_name)
                response = agent.call(context_pkg)
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
                    if not is_last_agent:
                        pending_proposal = (response, agent_name)
                        continue
                    self.handle_proposal(response, agent_name)
                    return
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
                    if pending_proposal:
                        response, agent_name = pending_proposal
                        self.handle_proposal(response, agent_name)
                        return
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
                response, agent_name = pending_proposal
                self.handle_proposal(response, agent_name)
                return

            if self.all_expected_agents_completed():
                self.stream.system("Round complete. Awaiting next instruction.")
                self.update_state({"status": "idle", "next_agent": "you"})
                return

        self.stream.escalate("Agents have not reached consensus. Your call.")
        self.update_state({"status": "awaiting_approval", "next_agent": "you"})

    def parse_signal(self, response: str) -> str | None:
        upper = response.upper()
        for signal in SIGNALS:
            if f">>> {signal}" in upper:
                return signal
        return None

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

        if verdict == "APPROVE":
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
        agent = self.router.get_agent(lead)
        context_pkg = self.context.build(self.state, self.chatboks_md)
        response = agent.execute(context_pkg)
        self.append_message(lead, response)
        signal = self.parse_signal(response)
        self.update_state({"status": "idle" if signal != "BLOCKED" else "blocked"})

    def check_token_limit(self, agent_name: str) -> None:
        agent_config = self.config["agents"][agent_name]
        current = self.state["context"]["token_counts"].get(agent_name, 0)
        warning = int(agent_config["token_warning"])

        if current >= warning:
            self.stream.system(f"{agent_name} approaching token limit. Summarizing.")
            summary = self.context.summarize(self.chatboks_md)
            agent = self.router.get_agent(agent_name)
            codegraph = self.context.load_codegraph()
            agent.reinitialize(codegraph, summary, self.state)
            self.append_message(
                "system",
                f"{agent_name} reinitialized. Context compressed and reloaded.",
            )
            self.state["context"]["token_counts"][agent_name] = 0
            self.save_state()

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
            return self.normalize_state(json.loads(self.state_file.read_text(encoding="utf-8")))
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
        state.setdefault("expected_agents", [])
        state.setdefault("completed_agents", [])
        state.setdefault("handoff_to", None)
        state.setdefault("handoff_reason", None)
        state.setdefault("handoff_context", None)
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
        if upper.startswith("MODIFY "):
            return True
        if stripped.startswith("@") and len(stripped.split()) <= 3:
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
