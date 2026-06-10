from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context.packets import extract_packets
from context.summarizer import Summarizer
from orchestrator import Chatboks


def _make_app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = {"agents": {"codex": {}}}
    app.proj_config = {"agents": ["codex"]}
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.packet_file = root / ".chatboks" / "packets.jsonl"
    app.stream = MagicMock()
    app.router = MagicMock()
    app.context = MagicMock()
    app._internal_write = False
    app.input_buffer = []
    app.state = app.normalize_state({"session": "test", "round": 7, "status": "active"})
    app.save_state = MagicMock()
    return app


def test_extract_packets_parses_valid_block():
    response = """Done.
>>> PACKET
agent: codex
stance: VERIFY
observed:
- pytest passed
- graph fresh
risks:
- none
next_action: commit
signal: TASK_COMPLETE
>>> PACKET_END
>>> TASK_COMPLETE
"""

    packets = extract_packets(response, fallback_agent="codex")

    assert len(packets) == 1
    packet = packets[0]
    assert packet.agent == "codex"
    assert packet.stance == "VERIFY"
    assert packet.observed == ["pytest passed", "graph fresh"]
    assert packet.risks == ["none"]
    assert packet.next_action == "commit"
    assert packet.signal == "TASK_COMPLETE"


def test_extract_packets_ignores_malformed_block():
    response = """Nope.
>>> PACKET
agent: codex
stance: MAYBE
signal: WHEE
>>> PACKET_END
>>> TASK_COMPLETE
"""

    assert extract_packets(response, fallback_agent="codex") == []


def test_append_message_persists_packet_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = _make_app(root)
        response = """Implemented.
>>> PACKET
stance: ADD
observed:
- parser stores packets
risks:
- malformed packets are ignored
next_action: run tests
signal: TASK_COMPLETE
>>> PACKET_END
>>> TASK_COMPLETE
"""

        app.append_message("codex", response)

        records = [json.loads(line) for line in app.packet_file.read_text(encoding="utf-8").splitlines()]
        assert len(records) == 1
        assert records[0]["sender"] == "codex"
        assert records[0]["round"] == 7
        assert records[0]["packet"]["agent"] == "codex"
        assert records[0]["packet"]["observed"] == ["parser stores packets"]
        assert ">>> PACKET" in app.chatboks_md.read_text(encoding="utf-8")


def test_summarizer_prefers_packet_memory():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        chat = root / "chatboks.md"
        chat.write_text(
            "[YOU] role call\n"
            "[CODEX] Codex online.\n"
            ">>> TASK_COMPLETE\n",
            encoding="utf-8",
        )
        packet_dir = root / ".chatboks"
        packet_dir.mkdir()
        (packet_dir / "packets.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-06-10T10:00:00",
                    "project": "test",
                    "sender": "codex",
                    "round": 1,
                    "packet": {
                        "agent": "codex",
                        "stance": "VERIFY",
                        "observed": ["sleep memory includes packet facts"],
                        "risks": ["packet schema still optional"],
                        "next_action": "review packet trace UX",
                        "signal": "TASK_COMPLETE",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        summary = Summarizer(max_items=8).summarize(chat)

        assert "Verified facts:" in summary
        assert "sleep memory includes packet facts" in summary
        assert "Open risks:" in summary
        assert "packet schema still optional" in summary
        assert "Pending tasks:" in summary
        assert "review packet trace UX" in summary
        assert "role call" not in summary.lower()


if __name__ == "__main__":
    test_extract_packets_parses_valid_block()
    test_extract_packets_ignores_malformed_block()
    test_append_message_persists_packet_jsonl()
    test_summarizer_prefers_packet_memory()
    print("\nAll packet smoke tests passed.")
