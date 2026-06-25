from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from rich.text import Text

from ui.stream import Stream

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Footer, Header, Input, RichLog, Static
except ImportError as exc:  # pragma: no cover - exercised by CLI error path
    raise RuntimeError(
        "Textual is not installed. Install dependencies with "
        "`python -m pip install -r requirements.txt`."
    ) from exc


class TextualStream:
    """Stream adapter that writes ChatBoks events into a Textual RichLog."""

    def __init__(self, app: "ChatboksTextualApp", fallback: Stream) -> None:
        self.app = app
        self.fallback = fallback

    def intro(self, project: str) -> None:
        self.app.write_log(f"CHATBOKS - {project.upper()}", "bold green")
        self.app.write_log("relay bus online - Textual pilot active", "dim green")

    def ready(self) -> None:
        self.app.set_status("ready")

    def token_usage(
        self,
        token_counts: dict[str, int],
        session_budget: dict[str, int] | None = None,
    ) -> None:
        self.app.set_token_line(self.fallback.build_token_usage_line(token_counts, session_budget))

    def agent_activity_start(self, agent_name: str, mode: str) -> None:
        self.app.set_status(f"{agent_name.upper()} working in {mode} mode")

    def agent_activity_finish(self, agent_name: str, mode: str, elapsed_seconds: float) -> None:
        if elapsed_seconds > 0:
            self.app.write_log(f"{agent_name.upper()} finished {mode} in {elapsed_seconds:.1f}s", "dim")
        self.app.set_status("ready")

    def agent_output_start(self, agent_name: str, mode: str) -> None:
        self.app.write_log(f"{agent_name.upper()} {mode} answer", "bold")

    def agent_output_delta(self, agent_name: str, text: str) -> None:
        if text:
            self.app.write_log(text.rstrip("\n"), self.agent_style(agent_name))

    def agent_output_finish(self, agent_name: str) -> None:
        self.app.write_log(f"{agent_name.upper()} answer complete", "dim")

    def role_call(self, agents: list[str], standby_agents: list[str] | None = None) -> None:
        names = ", ".join(agent.upper() for agent in agents)
        if standby_agents:
            names += " | standby: " + ", ".join(agent.upper() for agent in standby_agents)
        self.app.write_log(f"role call: {names}", "dim")

    def message(self, sender: str, text: str, timestamp: str) -> None:
        self.app.write_log(f"[{sender.upper()}] {timestamp}", "bold")
        self.app.write_log(text.strip(), self.agent_style(sender))

    def standby(self, agent_name: str, text: str) -> None:
        self.app.write_log(f"[{agent_name.upper()}] {text.strip()}", "dim")

    def system(self, text: str) -> None:
        self.app.write_log(f"[SYSTEM] {text}", "dim")

    def help_box(self, commands: list[tuple[str, str]]) -> None:
        lines = ["Command deck:"]
        lines.extend(f"{command:<24} {description}" for command, description in commands)
        self.app.write_log("\n".join(lines), "green")

    def help_pin(self, commands: list[str]) -> None:
        self.app.set_help_line("commands: " + "  ".join(commands))

    def proposal(self, text: str) -> None:
        self.app.write_log(text, "yellow")

    def question(self, text: str) -> None:
        self.app.write_log(f">>> {text}", "bold yellow")

    def escalate(self, text: str) -> None:
        self.app.write_log(f">>> {text}", "bold red")

    def prompt(self, label: str = "You > ") -> str:
        raise RuntimeError("Textual mode receives input through the prompt widget.")

    def agent_style(self, agent_name: str) -> str:
        return str(self.fallback.colors.get(agent_name.lower(), "white"))


class ChatboksTextualApp(App[None]):
    """Optional Textual shell for interactive ChatBoks sessions."""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #body {
        height: 1fr;
        layout: horizontal;
    }

    #left-rail {
        width: 28;
        padding: 1;
        border: solid $accent;
    }

    #transcript {
        width: 1fr;
        border: solid $primary;
    }

    #prompt {
        dock: bottom;
    }

    #status, #tokens, #help {
        height: auto;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear log"),
    ]

    def __init__(self, chatboks: Any) -> None:
        super().__init__()
        self.chatboks = chatboks
        self._worker_thread: threading.Thread | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="help")
        with Horizontal(id="body"):
            yield Static(self.agent_summary(), id="left-rail")
            yield RichLog(id="transcript")
        yield Static("status: starting", id="status")
        yield Static("session tokens: unavailable", id="tokens")
        yield Input(placeholder="Type a prompt, slash command, APPROVE, MODIFY, or REJECT", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        fallback = self.chatboks.stream
        self.chatboks.stream = TextualStream(self, fallback)
        self.chatboks.ensure_project_files()
        self.chatboks.stream.intro(self.chatboks.project)
        if self.chatboks.state.get("status") == "initializing":
            self.chatboks.initialize_agents()
        self.chatboks.stream.ready()
        self.chatboks.refresh_token_usage_display()
        self.chatboks.show_prompt_help_pin(force=True)
        self.seed_transcript_tail()
        self.query_one("#prompt", Input).focus()

    @on(Input.Submitted, "#prompt")
    def on_prompt_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        prompt = self.query_one("#prompt", Input)
        prompt.value = ""
        if not value:
            return
        self.write_log(f"[YOU] {value}", "bold")
        prompt.disabled = True
        self.set_status("working")
        thread = threading.Thread(target=self.process_prompt, args=(value,), daemon=True)
        self._worker_thread = thread
        thread.start()

    def process_prompt(self, value: str) -> None:
        try:
            self.chatboks.handle_user_input(value)
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.call_from_thread(self.write_log, f"[SYSTEM] TUI prompt failed: {exc}", "bold red")
        finally:
            self.call_from_thread(self.finish_prompt)

    def finish_prompt(self) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()
        self.set_status("ready")

    def write_log(self, message: str, style: str | None = None) -> None:
        if not message:
            return
        log = self.query_one("#transcript", RichLog)
        log.write(Text(message, style=style or ""))

    def set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(f"status: {text}")

    def set_token_line(self, text: str) -> None:
        self.query_one("#tokens", Static).update(text)

    def set_help_line(self, text: str) -> None:
        self.query_one("#help", Static).update(text)

    def seed_transcript_tail(self, line_count: int = 80) -> None:
        path = Path(self.chatboks.chatboks_md)
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        tail = "\n".join(lines[-line_count:]).strip()
        if tail:
            self.write_log("Recent transcript tail", "bold dim")
            self.write_log(tail, "dim")

    def action_clear_log(self) -> None:
        self.query_one("#transcript", RichLog).clear()

    def agent_summary(self) -> str:
        project = str(self.chatboks.project)
        mode = str(self.chatboks.state.get("collaboration_mode", "default"))
        status = str(self.chatboks.state.get("status", "unknown"))
        agents = ", ".join(self.chatboks.proj_config.get("agents", []))
        direct = ", ".join(self.chatboks.proj_config.get("direct_agents", [])) or "none"
        return (
            f"Project: {project}\n"
            f"Mode: {mode}\n"
            f"State: {status}\n\n"
            f"Agents:\n{agents}\n\n"
            f"Direct:\n{direct}\n\n"
            "Keys:\nCtrl+L clear\nCtrl+C quit"
        )


def run_textual_app(chatboks: Any) -> int:
    ChatboksTextualApp(chatboks).run()
    return 0
