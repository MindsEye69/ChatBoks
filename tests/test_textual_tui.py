from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.widgets import Input

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.stream import Stream
from ui.textual_app import ChatboksTextualApp, TextualStream


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


def test_textual_app_seed_transcript_tail_handles_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        chatboks = MagicMock()
        chatboks.chatboks_md = Path(tmp) / "missing.md"
        app = ChatboksTextualApp(chatboks)
        app.write_log = MagicMock()

        app.seed_transcript_tail()

        app.write_log.assert_not_called()


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
        prompt = app.query_one("#prompt", Input)
        assert prompt.placeholder.startswith("Type a prompt")
        chatboks.ensure_project_files.assert_called_once()
        chatboks.refresh_token_usage_display.assert_called_once()
        chatboks.show_prompt_help_pin.assert_called_once_with(force=True)
