from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.geometry import Offset
from textual.selection import Selection
from textual.widgets import OptionList, RichLog, Static, TextArea

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.stream import Stream
from ui.textual_app import ChatboksTextualApp, SelectableRichLog, TextualStream


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeTextualApp:
    def __init__(self) -> None:
        self.log: list[tuple[str, str | None]] = []
        self.status = ""
        self.tokens = ""
        self.help = ""

    def write_log(self, message: str, style: str | None = None) -> None:
        self.log.append((message, style))

    def set_status(self, text: str) -> None:
        self.status = text

    def set_token_line(self, text: str) -> None:
        self.tokens = text

    def set_help_line(self, text: str) -> None:
        self.help = text


def test_textual_stream_writes_core_chatboks_events() -> None:
    fake = FakeTextualApp()
    fallback = Stream({"codex": {"color": "green"}}, ["codex"])
    stream = TextualStream(fake, fallback)

    stream.intro("chatboks")
    stream.system("ready")
    stream.agent_output_start("codex", "respond")
    stream.agent_output_delta("codex", "hello")
    stream.agent_output_finish("codex")
    stream.token_usage({"codex": 12}, None)
    stream.help_pin(["/help", "exit"])

    messages = [message for message, _style in fake.log]
    assert "CHATBOKS - CHATBOKS" in messages
    assert "[SYSTEM] ready" in messages
    assert "CODEX respond answer" in messages
    assert "hello" in messages
    assert fake.tokens.startswith("session tokens:")
    assert "/help" in fake.help


def test_textual_stream_buffers_character_deltas_until_line_or_finish() -> None:
    fake = FakeTextualApp()
    fallback = Stream({"codex": {"color": "green"}}, ["codex"])
    stream = TextualStream(fake, fallback)

    stream.agent_output_start("codex", "respond")
    for char in "MindsEye":
        stream.agent_output_delta("codex", char)

    messages = [message for message, _style in fake.log]
    assert "MindsEye" not in messages
    assert "M" not in messages

    stream.agent_output_finish("codex")

    messages = [message for message, _style in fake.log]
    assert "MindsEye" in messages
    assert "M" not in messages
    assert "CODEX answer complete" in messages


def test_textual_stream_flushes_complete_lines_while_buffering_tail() -> None:
    fake = FakeTextualApp()
    fallback = Stream({"codex": {"color": "green"}}, ["codex"])
    stream = TextualStream(fake, fallback)

    stream.agent_output_start("codex", "respond")
    stream.agent_output_delta("codex", "first line\nsecond")

    messages = [message for message, _style in fake.log]
    assert "first line" in messages
    assert "second" not in messages

    stream.agent_output_finish("codex")

    messages = [message for message, _style in fake.log]
    assert "second" in messages


def test_textual_app_agent_summary_uses_project_state() -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "implement", "status": "active"}
    chatboks.proj_config = {"agents": ["claude", "codex"], "direct_agents": ["coordinator"]}

    app = ChatboksTextualApp(chatboks)
    summary = app.agent_summary()

    assert "Project: chatboks" in summary
    assert "Mode: implement" in summary
    assert "State: active" in summary
    assert "claude, codex" in summary
    assert "coordinator" in summary
    assert "F8 copy selection" in summary
    assert summary.count("\n") == 2


def test_textual_app_seed_transcript_tail_handles_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        chatboks = MagicMock()
        chatboks.chatboks_md = Path(tmp) / "missing.md"
        app = ChatboksTextualApp(chatboks)
        app.write_log = MagicMock()

        app.seed_transcript_tail()

        app.write_log.assert_not_called()


def test_textual_app_completion_palette_covers_fixed_choice_commands() -> None:
    chatboks = MagicMock()
    chatboks.config = {"agents": {"codex": {}, "claude": {}}}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": ["coordinator"]}
    chatboks.list_native_skills.return_value = [("implement", "implementation workflow")]
    app = ChatboksTextualApp(chatboks)

    assert ("/mode brainstorm", "Brainstorm mode") in app.completion_options("/mode br")
    assert ("/context lean", "small context package") in app.completion_options("/context l")
    assert ("/agent codex", "configured agent") in app.completion_options("/agent co")
    assert ("/agent codex exhausted", "temporarily skip this agent") in app.completion_options("/agent codex ")
    assert ("/usage sync", "capture provider usage baseline") in app.completion_options("/usage s")
    assert ("/usage sync openai", "OpenAI Platform") in app.completion_options("/usage sync ")
    assert ("/usage sync openai", "OpenAI Platform") in app.completion_options("/usage sync op")
    assert ("/skills implement", "implementation workflow") in app.completion_options("/skills im")
    assert ("/tickets all", "show all Paper Sleuth tickets") in app.completion_options("/tickets ")
    assert ("/tickets open", "show open Paper Sleuth tickets") in app.completion_options("/tickets o")
    assert ("@codex", "route directly to agent") in app.completion_options("@co")
    assert ("/session start", "run DasDashboard start checks") in app.completion_options("/session st")
    assert ("/session close", "run DasDashboard close checks") in app.completion_options("/session cl")
    assert app.completion_options("/model-commands") == []
    assert app.replacement_from_option_prompt("/mode brainstorm            Brainstorm mode") == "/mode brainstorm"
    long_replacement = "/agent very_long_custom_agent_name exhausted"
    option_prompt = app.format_completion_option(long_replacement, "temporarily skip this agent")
    assert app.replacement_from_option_prompt(option_prompt) == long_replacement


@pytest.mark.anyio
async def test_textual_app_mounts_with_fake_chatboks(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": ["coordinator"]}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.chatboks_md.write_text("[SYSTEM] prior line\n", encoding="utf-8")
    chatboks.stream = Stream({"codex": {"color": "green"}}, ["codex"])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    app = ChatboksTextualApp(chatboks)
    async with app.run_test():
        prompt = app.query_one("#prompt", TextArea)
        transcript = app.query_one("#transcript", RichLog)
        assert prompt.placeholder.startswith("Type a prompt")
        assert prompt.styles.height.value == 4
        assert transcript.allow_select is True
        assert isinstance(transcript, SelectableRichLog)
        child_ids = [child.id for child in app.screen.children if child.id]
        assert child_ids.index("tokens") < child_ids.index("transcript")
        child_types = [type(child).__name__ for child in app.screen.children]
        assert child_types.index("PromptTextArea") < child_types.index("Footer")
        chatboks.ensure_project_files.assert_called_once()
        chatboks.refresh_token_usage_display.assert_called_once()
        chatboks.show_prompt_help_pin.assert_called_once_with(force=True)


@pytest.mark.anyio
async def test_textual_app_copies_transcript_without_selection(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": []}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.stream = Stream({}, [])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    copied: list[str] = []
    app = ChatboksTextualApp(chatboks)
    async with app.run_test():
        app.copy_text_to_clipboard = lambda text: copied.append(text) or "test"  # type: ignore[method-assign]
        app.write_log("line one\nline two", "green")

        app.action_select_transcript()
        assert "line one\nline two" in app.selected_text()

        app.action_copy_selection()

        assert copied
        assert "line one\nline two" in copied[-1]

        app.action_clear_log()
        assert app.transcript_text() == ""


@pytest.mark.anyio
async def test_textual_app_does_not_copy_without_selection(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": []}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.stream = Stream({}, [])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    copied: list[str] = []
    app = ChatboksTextualApp(chatboks)
    async with app.run_test():
        app.copy_text_to_clipboard = lambda text: copied.append(text) or "test"  # type: ignore[method-assign]
        app.action_clear_log()
        app.write_log("line one\nline two", "green")

        app.action_copy_selection()

        assert copied == []
        assert "nothing selected" in str(app.query_one("#status", Static).render())


@pytest.mark.anyio
async def test_textual_app_copies_local_transcript_selection(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": []}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.stream = Stream({}, [])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    copied: list[str] = []
    app = ChatboksTextualApp(chatboks)
    async with app.run_test():
        app.copy_text_to_clipboard = lambda text: copied.append(text) or "test"  # type: ignore[method-assign]
        transcript = app.query_one("#transcript", SelectableRichLog)
        app.action_clear_log()
        app.write_log("alpha beta\ngamma delta", "green")
        transcript._local_selection = Selection.from_offsets(Offset(6, 0), Offset(11, 0))

        app.action_copy_selection()

        assert copied == ["beta"]


@pytest.mark.anyio
async def test_textual_app_renders_full_line_selection(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": []}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.stream = Stream({}, [])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    app = ChatboksTextualApp(chatboks)
    async with app.run_test():
        app.write_log("selected whole line", "green")
        transcript = app.query_one("#transcript", SelectableRichLog)
        app.action_select_transcript()

        rendered = transcript.render_line(0)

        assert rendered.text.strip()


@pytest.mark.anyio
async def test_textual_app_shows_completion_palette_and_selects_mode(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": []}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.stream = Stream({}, [])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    app = ChatboksTextualApp(chatboks)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", TextArea)
        prompt.load_text("/mode br")
        app.update_completion_palette(prompt.text)
        palette = app.query_one("#completion-palette", OptionList)

        assert palette.display is True
        assert palette.option_count == 1
        assert "brainstorm" in str(palette.get_option_at_index(0).prompt)

        palette.highlighted = 0
        await pilot.press("enter")
        assert prompt.text == "/mode brainstorm"
        assert palette.display is False


@pytest.mark.anyio
async def test_textual_app_completion_palette_keyboard_navigation(tmp_path: Path) -> None:
    chatboks = MagicMock()
    chatboks.project = "chatboks"
    chatboks.state = {"collaboration_mode": "default", "status": "active"}
    chatboks.proj_config = {"agents": ["codex"], "direct_agents": []}
    chatboks.chatboks_md = tmp_path / "chatboks.md"
    chatboks.stream = Stream({}, [])
    chatboks.ensure_project_files = MagicMock()
    chatboks.initialize_agents = MagicMock()
    chatboks.refresh_token_usage_display = MagicMock()
    chatboks.show_prompt_help_pin = MagicMock()

    app = ChatboksTextualApp(chatboks)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", TextArea)
        prompt.load_text("/mode ")
        app.update_completion_palette(prompt.text)
        palette = app.query_one("#completion-palette", OptionList)
        original = palette.highlighted

        await pilot.press("down")
        assert palette.highlighted != original

        await pilot.press("tab")
        assert prompt.text.startswith("/mode ")
        assert prompt.text != "/mode "
        assert palette.display is False
