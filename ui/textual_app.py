from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from rich.text import Text

from ui.stream import Stream

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.events import Key, MouseDown, MouseMove, MouseUp
    from textual.geometry import Offset
    from textual.selection import Selection
    from textual.strip import Strip
    from textual.widgets import Footer, Header, OptionList, RichLog, Static, TextArea
except ImportError as exc:  # pragma: no cover - exercised by CLI error path
    raise RuntimeError(
        "Textual is not installed. Install dependencies with "
        "`python -m pip install -r requirements.txt`."
    ) from exc


class SelectableRichLog(RichLog):
    """RichLog variant that paints and extracts Textual text selections."""

    def __init__(self, *args: Any, text_provider: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._text_provider = text_provider
        self._local_selection: Selection | None = None
        self._selection_anchor: Offset | None = None

    def selection_source_text(self) -> str:
        if self._text_provider is not None:
            return str(self._text_provider())
        return "\n".join(line.text for line in self.lines)

    def selected_text(self) -> str:
        selection = self._local_selection or self.text_selection
        if selection is None:
            return ""
        return selection.extract(self.selection_source_text())

    def clear_local_selection(self) -> None:
        self._local_selection = None
        self._selection_anchor = None
        self.refresh()

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        return selection.extract(self.selection_source_text()), "\n"

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        content_y = scroll_y + y
        width = self.scrollable_content_region.width
        line = self._render_line(content_y, scroll_x, width).apply_style(self.rich_style)
        selection = self._local_selection or self.text_selection
        if selection is None:
            return line
        span = selection.get_span(content_y)
        if span is None:
            return line

        start, end = span
        visible_start = max(0, min(line.cell_length, start - scroll_x))
        visible_end = line.cell_length if end == -1 else max(0, min(line.cell_length, end - scroll_x))
        if visible_end <= visible_start:
            return line

        selection_style = self.screen.get_component_rich_style("screen--selection")
        pieces = []
        if visible_start > 0:
            pieces.append(line.crop(0, visible_start))
        pieces.append(line.crop(visible_start, visible_end).apply_style(selection_style))
        if visible_end < line.cell_length:
            pieces.append(line.crop(visible_end, line.cell_length))
        return Strip.join(pieces)

    def event_content_offset(self, event: MouseDown | MouseMove | MouseUp) -> Offset:
        x = max(0, int(event.x) + self.scroll_offset.x)
        y = max(0, int(event.y) + self.scroll_offset.y)
        return Offset(x, y)

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            return
        self.screen.clear_selection()
        self._selection_anchor = self.event_content_offset(event)
        self._local_selection = Selection.from_offsets(self._selection_anchor, self._selection_anchor)
        self.capture_mouse()
        self.focus()
        self.refresh()
        event.prevent_default()
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self._selection_anchor is None:
            return
        self._local_selection = Selection.from_offsets(self._selection_anchor, self.event_content_offset(event))
        self.refresh()
        event.prevent_default()
        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        if self._selection_anchor is None:
            return
        self._local_selection = Selection.from_offsets(self._selection_anchor, self.event_content_offset(event))
        self._selection_anchor = None
        self.release_mouse()
        self.refresh()
        event.prevent_default()
        event.stop()


class PromptTextArea(TextArea):
    """Four-line prompt that submits on Enter."""

    def on_key(self, event: Key) -> None:
        if event.key != "enter":
            return
        app = self.app
        if hasattr(app, "completion_palette_visible") and app.completion_palette_visible():
            app.select_highlighted_completion()
        elif hasattr(app, "submit_prompt_text"):
            app.submit_prompt_text()
        event.prevent_default()
        event.stop()


class TextualStream:
    """Stream adapter that writes ChatBoks events into a Textual RichLog."""

    def __init__(self, app: "ChatboksTextualApp", fallback: Stream) -> None:
        self.app = app
        self.fallback = fallback
        self._agent_output_buffers: dict[str, str] = {}

    def call_ui(self, method_name: str, *args: Any) -> None:
        dispatcher = getattr(self.app, "call_ui", None)
        if dispatcher is not None:
            dispatcher(method_name, *args)
            return
        getattr(self.app, method_name)(*args)

    def log(self, message: str, style: str | None = None) -> None:
        self.call_ui("write_log", message, style)

    def intro(self, project: str) -> None:
        self.log(f"CHATBOKS - {project.upper()}", "bold green")
        self.log("relay bus online - Textual pilot active", "dim green")

    def ready(self) -> None:
        self.call_ui("set_status", "ready")

    def token_usage(
        self,
        token_counts: dict[str, int],
        session_budget: dict[str, int] | None = None,
    ) -> None:
        self.call_ui("set_token_line", self.fallback.build_token_usage_line(token_counts, session_budget))

    def agent_activity_start(self, agent_name: str, mode: str) -> None:
        self.call_ui("set_status", f"{agent_name.upper()} working in {mode} mode")

    def agent_activity_finish(self, agent_name: str, mode: str, elapsed_seconds: float) -> None:
        if elapsed_seconds > 0:
            self.log(f"{agent_name.upper()} finished {mode} in {elapsed_seconds:.1f}s", "dim")
        self.call_ui("set_status", "ready")

    def agent_output_start(self, agent_name: str, mode: str) -> None:
        self._agent_output_buffers[agent_name.lower()] = ""
        self.log(f"{agent_name.upper()} {mode} answer", "bold")

    def agent_output_delta(self, agent_name: str, text: str) -> None:
        if not text:
            return
        key = agent_name.lower()
        buffer = self._agent_output_buffers.get(key, "") + text
        style = self.agent_style(agent_name)
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            self.log(line.rstrip("\r"), style)
        self._agent_output_buffers[key] = buffer

    def agent_output_finish(self, agent_name: str) -> None:
        key = agent_name.lower()
        remaining = self._agent_output_buffers.pop(key, "")
        if remaining:
            self.log(remaining.rstrip("\r\n"), self.agent_style(agent_name))
        self.log(f"{agent_name.upper()} answer complete", "dim")

    def role_call(self, agents: list[str], standby_agents: list[str] | None = None) -> None:
        names = ", ".join(agent.upper() for agent in agents)
        if standby_agents:
            names += " | standby: " + ", ".join(agent.upper() for agent in standby_agents)
        self.log(f"role call: {names}", "dim")

    def message(self, sender: str, text: str, timestamp: str) -> None:
        self.log(f"[{sender.upper()}] {timestamp}", "bold")
        self.log(text.strip(), self.agent_style(sender))

    def standby(self, agent_name: str, text: str) -> None:
        self.log(f"[{agent_name.upper()}] {text.strip()}", "dim")

    def system(self, text: str) -> None:
        self.log(f"[SYSTEM] {text}", "dim")

    def help_box(self, commands: list[tuple[str, str]]) -> None:
        lines = ["Command deck:"]
        lines.extend(f"{command:<24} {description}" for command, description in commands)
        self.log("\n".join(lines), "green")

    def help_pin(self, commands: list[str]) -> None:
        self.call_ui("set_help_line", "commands: " + "  ".join(commands))

    def proposal(self, text: str) -> None:
        self.log(text, "yellow")

    def question(self, text: str) -> None:
        self.log(f">>> {text}", "bold yellow")

    def escalate(self, text: str) -> None:
        self.log(f">>> {text}", "bold red")

    def prompt(self, label: str = "You > ") -> str:
        raise RuntimeError("Textual mode receives input through the prompt widget.")

    def agent_style(self, agent_name: str) -> str:
        return str(self.fallback.colors.get(agent_name.lower(), "white"))


class ChatboksTextualApp(App[None]):
    """Optional Textual shell for interactive ChatBoks sessions."""

    TITLE = "ChatBoks"
    SUB_TITLE = "Textual pilot"

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    Screen > .screen--selection {
        background: #0f4a78;
        color: #ffffff;
    }

    #left-rail {
        width: 1fr;
        height: auto;
        padding: 0 1;
        border: solid $accent;
    }

    #transcript {
        width: 1fr;
        height: 1fr;
        border: solid $primary;
    }

    #prompt {
        height: 4;
    }

    #completion-palette {
        height: auto;
        max-height: 9;
        border: solid $success;
        display: none;
    }

    #status, #tokens, #help {
        height: auto;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("f8", "copy_selection", "Copy"),
        ("f7", "select_transcript", "Select log"),
        ("f6", "focus_transcript", "Log"),
        ("f5", "focus_prompt", "Prompt"),
        ("ctrl+shift+c", "copy_selection", "Copy"),
        ("ctrl+shift+a", "select_transcript", "Select log"),
        ("ctrl+t", "focus_transcript", "Log"),
        ("ctrl+p", "focus_prompt", "Prompt"),
    ]

    def __init__(self, chatboks: Any) -> None:
        super().__init__()
        self.chatboks = chatboks
        self._worker_thread: threading.Thread | None = None
        self._app_thread_id: int | None = None
        self._transcript_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="help")
        yield Static("session tokens: unavailable", id="tokens")
        yield SelectableRichLog(id="transcript", text_provider=self.transcript_text)
        yield Static(self.agent_summary(), id="left-rail")
        yield Static("status: starting", id="status")
        yield OptionList(id="completion-palette")
        yield PromptTextArea(
            "",
            id="prompt",
            show_line_numbers=False,
            soft_wrap=True,
            tab_behavior="focus",
            placeholder="Type a prompt, slash command, APPROVE, MODIFY, or REJECT",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._app_thread_id = threading.get_ident()
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
        self.query_one("#prompt", PromptTextArea).focus()

    def on_key(self, event: Key) -> None:
        if self.completion_palette_visible():
            if event.key == "down":
                self.move_completion_highlight(1)
                event.prevent_default()
                event.stop()
            elif event.key == "up":
                self.move_completion_highlight(-1)
                event.prevent_default()
                event.stop()
            elif event.key in {"tab", "enter"}:
                self.select_highlighted_completion()
                event.prevent_default()
                event.stop()
            elif event.key == "escape":
                self.hide_completion_palette()
                event.prevent_default()
                event.stop()
            return

        focused = self.screen.focused
        if isinstance(focused, TextArea) and focused.id == "prompt" and event.key == "enter" and not event.shift:
            self.submit_prompt_text()
            event.prevent_default()
            event.stop()

    @on(TextArea.Changed, "#prompt")
    def on_prompt_changed(self, event: TextArea.Changed) -> None:
        self.update_completion_palette(event.text_area.text)

    @on(OptionList.OptionSelected, "#completion-palette")
    def on_completion_option_selected(self, event: OptionList.OptionSelected) -> None:
        replacement = self.replacement_from_option_prompt(str(event.option.prompt))
        if not replacement:
            return
        prompt = self.query_one("#prompt", TextArea)
        self.set_prompt_text(prompt, replacement)
        self.hide_completion_palette()
        prompt.focus()

    def submit_prompt_text(self) -> None:
        prompt = self.query_one("#prompt", TextArea)
        if self.select_highlighted_completion():
            return
        value = prompt.text.strip()
        prompt.clear()
        self.hide_completion_palette()
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
        prompt = self.query_one("#prompt", TextArea)
        prompt.disabled = False
        prompt.focus()
        self.refresh_left_rail()
        self.set_status("ready")

    def set_prompt_text(self, prompt: TextArea, text: str) -> None:
        prompt.load_text(text)
        lines = text.splitlines() or [""]
        prompt.move_cursor((len(lines) - 1, len(lines[-1])))

    def write_log(self, message: str, style: str | None = None) -> None:
        if not message:
            return
        self.remember_transcript_text(message)
        log = self.query_one("#transcript", RichLog)
        log.write(Text(message, style=style or ""))

    def remember_transcript_text(self, message: str) -> None:
        self._transcript_lines.extend(message.splitlines() or [message])
        if len(self._transcript_lines) > 2000:
            del self._transcript_lines[:-2000]

    def transcript_text(self) -> str:
        return "\n".join(self._transcript_lines).strip()

    def selected_text(self) -> str:
        try:
            log_selection = self.query_one("#transcript", SelectableRichLog).selected_text().strip()
            if log_selection:
                return log_selection
        except Exception:
            pass
        try:
            return (self.screen.get_selected_text() or "").strip()
        except Exception:
            return ""

    def call_ui(self, method_name: str, *args: Any) -> None:
        method = getattr(self, method_name)
        if self._app_thread_id is None or threading.get_ident() == self._app_thread_id:
            method(*args)
            return
        self.call_from_thread(method, *args)

    def set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(f"status: {text}")

    def set_token_line(self, text: str) -> None:
        self.query_one("#tokens", Static).update(text)

    def set_help_line(self, text: str) -> None:
        self.query_one("#help", Static).update(text)

    def update_completion_palette(self, value: str) -> None:
        options = self.completion_options(value)
        if not options:
            self.hide_completion_palette()
            return
        palette = self.query_one("#completion-palette", OptionList)
        palette.set_options([self.format_completion_option(replacement, label) for replacement, label in options])
        palette.display = True
        palette.highlighted = 0

    def hide_completion_palette(self) -> None:
        palette = self.query_one("#completion-palette", OptionList)
        palette.display = False
        palette.clear_options()

    def completion_palette_visible(self) -> bool:
        palette = self.query_one("#completion-palette", OptionList)
        return bool(palette.display and palette.option_count > 0)

    def move_completion_highlight(self, delta: int) -> None:
        palette = self.query_one("#completion-palette", OptionList)
        if palette.option_count <= 0:
            return
        current = palette.highlighted
        if current is None or current < 0:
            current = 0
        palette.highlighted = (current + delta) % palette.option_count

    def select_highlighted_completion(self) -> bool:
        palette = self.query_one("#completion-palette", OptionList)
        if not self.completion_palette_visible():
            return False
        index = palette.highlighted
        if index is None or index < 0:
            index = 0
        option = palette.get_option_at_index(index)
        replacement = self.replacement_from_option_prompt(str(option.prompt))
        if not replacement:
            return False
        prompt = self.query_one("#prompt", TextArea)
        self.set_prompt_text(prompt, replacement)
        self.hide_completion_palette()
        prompt.focus()
        return True

    def completion_options(self, value: str) -> list[tuple[str, str]]:
        stripped = value.lstrip()
        if not stripped.startswith(("/", "@")):
            return []
        parts = stripped.split()
        trailing_space = stripped.endswith(" ")
        command = parts[0].lower() if parts else stripped.lower()

        if command in {"/mode", "/modes"}:
            return self.complete_word_command(stripped, "/mode", self.mode_choice_labels())
        if command in {"/context", "/ctx"}:
            return self.complete_word_command(
                stripped,
                "/context",
                {
                    "lean": "small context package",
                    "normal": "standard context package",
                    "full": "maximum broad context",
                },
            )
        if command in {"/help", "/h", "/?"}:
            return self.complete_word_command(
                stripped,
                "/help",
                {
                    "compact": "show compact command strip once",
                    "pin": "show command strip before prompts",
                    "unpin": "hide command strip before prompts",
                },
            )
        if command in {"/sleep", "/memory"}:
            return self.complete_word_command(
                stripped,
                command,
                {
                    "status": "show latest session memory",
                    "show": "show latest session memory",
                    "latest": "show latest session memory",
                    "run": "consolidate session memory",
                    "now": "consolidate session memory",
                },
            )
        if command in {"/test", "/tests"}:
            return self.complete_word_command(
                stripped,
                "/test",
                {
                    "confirmation-risk": "local confirmation packet risk smoke",
                    "packet-risk": "alias for confirmation-risk",
                },
            )
        if command in {"/ticket", "/tickets"}:
            return self.complete_word_command(
                stripped,
                "/tickets",
                {
                    "open": "show open Paper Sleuth tickets",
                    "all": "show all Paper Sleuth tickets",
                },
            )
        if command == "/outcome":
            return self.complete_word_command(
                stripped,
                "/outcome",
                {
                    "win": "record a positive collaboration outcome",
                    "failure": "record a failed collaboration outcome",
                },
            )
        if command == "/session":
            return self.complete_word_command(
                stripped,
                "/session",
                {
                    "start": "run DasDashboard start checks",
                    "close": "run DasDashboard close checks",
                },
            )
        if command in {"/skills", "/skill"}:
            return self.complete_word_command(stripped, "/skills", self.skill_choice_labels())
        if command == "/usage":
            return self.complete_usage_command(stripped, parts, trailing_space)
        if command in {"/agent", "/agents"}:
            return self.complete_agent_command(stripped, parts, trailing_space)
        if stripped.startswith("@") and len(parts) <= 1:
            return self.complete_agent_route(stripped)
        return []

    def complete_word_command(
        self,
        stripped: str,
        command: str,
        choices: dict[str, str],
    ) -> list[tuple[str, str]]:
        parts = stripped.split()
        trailing_space = stripped.endswith(" ")
        if len(parts) == 1 and not trailing_space:
            prefix = ""
        elif len(parts) <= 2:
            prefix = "" if trailing_space else parts[1].lower()
        else:
            return []
        if prefix in choices:
            return []
        return [
            (f"{command} {choice}", description)
            for choice, description in sorted(choices.items())
            if choice.startswith(prefix)
        ]

    def complete_usage_command(
        self,
        stripped: str,
        parts: list[str],
        trailing_space: bool,
    ) -> list[tuple[str, str]]:
        first_choices = {"sync": "capture provider usage baseline", "status": "show saved usage baselines"}
        if len(parts) <= 3 and len(parts) >= 2 and parts[1].lower() == "sync":
            prefix = "" if trailing_space or len(parts) == 2 else parts[2].lower()
            providers = self.usage_provider_choice_labels()
            if prefix in providers:
                return []
            return [
                (f"/usage sync {provider}", label)
                for provider, label in sorted(providers.items())
                if provider.startswith(prefix)
            ]
        if len(parts) == 1 and not trailing_space:
            return [(f"/usage {choice}", desc) for choice, desc in first_choices.items()]
        if len(parts) <= 2:
            prefix = "" if trailing_space else parts[1].lower()
            if prefix in first_choices:
                return []
            return [
                (f"/usage {choice}", desc)
                for choice, desc in sorted(first_choices.items())
                if choice.startswith(prefix)
            ]
        return []

    def complete_agent_command(
        self,
        stripped: str,
        parts: list[str],
        trailing_space: bool,
    ) -> list[tuple[str, str]]:
        agents = self.agent_choice_labels()
        statuses = self.agent_status_choice_labels()
        if len(parts) == 1 and not trailing_space:
            return [(f"/agent {agent}", label) for agent, label in sorted(agents.items())]
        if len(parts) <= 2 and not trailing_space:
            prefix = parts[1].lower()
            if prefix in agents:
                return []
            return [
                (f"/agent {agent}", label)
                for agent, label in sorted(agents.items())
                if agent.startswith(prefix)
            ]
        if len(parts) <= 3:
            agent = parts[1].lower() if len(parts) > 1 else ""
            if agent not in agents:
                return []
            prefix = "" if trailing_space else parts[2].lower()
            if prefix in statuses:
                return []
            return [
                (f"/agent {agent} {status}", label)
                for status, label in sorted(statuses.items())
                if status.startswith(prefix)
            ]
        return []

    def complete_agent_route(self, stripped: str) -> list[tuple[str, str]]:
        prefix = stripped[1:].lower()
        routes = self.agent_route_choice_labels()
        return [
            (route, label)
            for route, label in sorted(routes.items())
            if route[1:].startswith(prefix)
        ]

    def mode_choice_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for mode, instruction in self.mode_instructions().items():
            labels[mode] = instruction.split(".")[0].strip() or "collaboration mode"
        labels["reset"] = "alias for default"
        labels["standard"] = "alias for default"
        return labels

    def agent_choice_labels(self) -> dict[str, str]:
        config = getattr(self.chatboks, "config", {}) or {}
        agents = config.get("agents", {}) if isinstance(config, dict) else {}
        if not agents:
            names = list(getattr(self.chatboks, "proj_config", {}).get("agents", []))
            names.extend(getattr(self.chatboks, "proj_config", {}).get("direct_agents", []))
            agents = {name: {} for name in names}
        return {str(agent): "configured agent" for agent in sorted(agents)}

    @staticmethod
    def agent_status_choice_labels() -> dict[str, str]:
        return {
            "available": "ready for normal routing",
            "low": "usable but constrained",
            "exhausted": "temporarily skip this agent",
            "blocked": "unavailable until fixed",
            "ready": "alias for available",
            "awake": "alias for available",
            "wake": "alias for available",
        }

    def usage_provider_choice_labels(self) -> dict[str, str]:
        import orchestrator

        providers = {
            key: str(value.get("label") or key)
            for key, value in orchestrator.USAGE_PROVIDERS.items()
        }
        config = getattr(self.chatboks, "config", {}) or {}
        configured = config.get("usage_providers", {}) if isinstance(config, dict) else {}
        for key, value in configured.items():
            providers[str(key)] = str(value.get("label") or key) if isinstance(value, dict) else str(key)
        providers["all"] = "sync every known provider"
        return providers

    def skill_choice_labels(self) -> dict[str, str]:
        try:
            skills = self.chatboks.list_native_skills()
        except Exception:
            skills = []
        return {str(name): str(summary or "native workflow skill") for name, summary in skills}

    def agent_route_choice_labels(self) -> dict[str, str]:
        routes = {"@all": "route to all configured main agents"}
        for agent in self.agent_choice_labels():
            routes[f"@{agent}"] = "route directly to agent"
        routes["@spark"] = "route to Codex Spark"
        routes["@agy"] = "route to Antigravity"
        return routes

    @staticmethod
    def format_completion_option(replacement: str, label: str) -> str:
        return f"{replacement:<28}    {label}"

    @staticmethod
    def replacement_from_option_prompt(prompt: str) -> str:
        replacement, _separator, _label = prompt.partition("    ")
        return replacement.strip()

    def mode_instructions(self) -> dict[str, str]:
        import orchestrator

        return dict(orchestrator.COLLABORATION_MODES)

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
        self._transcript_lines.clear()

    def action_copy_selection(self) -> None:
        text = self.selected_text()
        if not text:
            self.set_status("nothing selected")
            return
        copy_method = self.copy_text_to_clipboard(text)
        if copy_method:
            self.set_status(f"copied {len(text)} chars via {copy_method}")
        else:
            self.set_status("copy failed")

    def copy_text_to_clipboard(self, text: str) -> str | None:
        if os.name == "nt":
            try:
                self.copy_text_to_windows_clipboard(text)
                return "win32"
            except Exception:
                pass
            try:
                subprocess.run(
                    ["clip.exe"],
                    input=text,
                    text=True,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
                return "clip.exe"
            except Exception:
                pass
        try:
            self.copy_to_clipboard(text)
            return "textual"
        except Exception:
            return None

    @staticmethod
    def copy_text_to_windows_clipboard(text: str) -> None:
        import ctypes

        cf_unicode_text = 13
        gmem_moveable = 0x0002
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_int
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.restype = ctypes.c_void_p

        data = (text + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(gmem_moveable, len(data))
        if not handle:
            raise OSError("GlobalAlloc failed")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            raise OSError("GlobalLock failed")
        try:
            ctypes.memmove(locked, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)

        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(handle)
            raise OSError("OpenClipboard failed")
        try:
            if not user32.EmptyClipboard():
                raise OSError("EmptyClipboard failed")
            if not user32.SetClipboardData(cf_unicode_text, handle):
                raise OSError("SetClipboardData failed")
            handle = None
        finally:
            user32.CloseClipboard()
            if handle:
                kernel32.GlobalFree(handle)

    def action_select_transcript(self) -> None:
        log = self.query_one("#transcript", SelectableRichLog)
        log.clear_local_selection()
        log.focus()
        log.text_select_all()
        self.set_status("transcript selected")

    def action_focus_transcript(self) -> None:
        self.query_one("#transcript", RichLog).focus()
        self.set_status("transcript focused")

    def action_focus_prompt(self) -> None:
        self.query_one("#prompt", TextArea).focus()
        self.set_status("ready")

    def refresh_left_rail(self) -> None:
        self.query_one("#left-rail", Static).update(self.agent_summary())

    def agent_summary(self) -> str:
        project = str(self.chatboks.project)
        mode = str(self.chatboks.state.get("collaboration_mode", "default"))
        status = str(self.chatboks.state.get("status", "unknown"))
        agents = ", ".join(self.chatboks.proj_config.get("agents", [])) or "none"
        direct = ", ".join(self.chatboks.proj_config.get("direct_agents", [])) or "none"
        return (
            f"Project: {project} | Mode: {mode} | State: {status}\n"
            f"Agents: {agents} | Direct: {direct}\n"
            "Keys: F8 copy selection | F7 select all | F6 log | F5 prompt | Ctrl+L clear | Ctrl+C quit"
        )


def run_textual_app(chatboks: Any) -> int:
    ChatboksTextualApp(chatboks).run()
    return 0
