"""Smoke tests for agent availability and exhausted-agent routing."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import Chatboks
from router import RoutingDecision


def _make_app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = {
        "projects": {
            "test": {
                "path": str(root),
                "agents": ["claude", "codex"],
                "primary": "claude",
            }
        },
        "agents": {
            "claude": {},
            "codex": {},
            "agent_zero": {},
        },
    }
    app.proj_config = app.config["projects"]["test"]
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.stream = MagicMock()
    app.router = MagicMock()
    app.router.primary.return_value = "claude"
    app.router.route_user_prompt_details.side_effect = lambda text, **_kwargs: (
        RoutingDecision(["claude"], text.removeprefix("@claude").strip(), "claude")
        if text.startswith("@claude")
        else RoutingDecision(["claude", "codex"], text)
    )
    app.context = MagicMock()
    app._internal_write = False
    app.input_buffer = []
    app.state = Chatboks.normalize_state(
        app,
        {
            "session": "test",
            "round": 0,
            "status": "active",
            "context": {"token_counts": {}},
        },
    )
    app.save_state = MagicMock()
    return app


def test_agent_command_marks_exhausted_without_agent_round():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/agent claude exhausted 50m")

        statuses = app.load_agent_statuses()
        assert statuses["claude"]["status"] == "exhausted"
        assert statuses["claude"].get("exhausted_until")
        assert "until" not in statuses["claude"]
        datetime.fromisoformat(statuses["claude"]["exhausted_until"])
        app.run_agent_round.assert_not_called()
        print("PASS: /agent marks exhausted without routing to agents")


def test_exhausted_command_accepts_duration_and_clock_time():
    now = datetime(2026, 6, 4, 14, 30).astimezone()

    in_60m = Chatboks.parse_status_until_at("60m", now)
    in_2h = Chatboks.parse_status_until_at("2h", now)
    clock = Chatboks.parse_status_until_at("3:17", now)
    padded_clock = Chatboks.parse_status_until_at("03:17", now)
    until_clock = Chatboks.parse_status_until_at("until 3:17", now)

    assert datetime.fromisoformat(in_60m) == now + timedelta(minutes=60)
    assert datetime.fromisoformat(in_2h) == now + timedelta(hours=2)
    assert datetime.fromisoformat(clock) == now.replace(hour=3, minute=17, second=0, microsecond=0) + timedelta(days=1)
    assert padded_clock == clock
    assert until_clock == clock
    print("PASS: exhausted command accepts duration and local clock times")


def test_expired_exhaustion_auto_clears_on_display():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        expired = (datetime.now().astimezone() - timedelta(minutes=1)).isoformat(timespec="seconds")
        app.save_agent_statuses({"claude": {"status": "exhausted", "updated_at": app.timestamp(), "exhausted_until": expired}})

        app.show_agent_statuses("claude")

        statuses = app.load_agent_statuses()
        assert statuses["claude"]["status"] == "available"
        message = app.stream.system.call_args.args[0]
        assert "- claude: available" in message
        print("PASS: expired exhaustion auto-clears on display")


def test_normal_round_substitutes_exhausted_agent():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.save_agent_statuses({"claude": {"status": "exhausted", "updated_at": app.timestamp()}})
        app.run_agent_round = MagicMock()

        app.handle_user_input("please inspect this")

        app.run_agent_round.assert_called_once()
        _, kwargs = app.run_agent_round.call_args
        assert kwargs["agents"] == ["codex"]
        assert app.state["next_agent"] == "codex"
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        assert "[SYSTEM] Agent availability: substituting codex for exhausted claude." in transcript
        print("PASS: normal route substitutes exhausted agent")


def test_direct_fallback_must_be_allowed_to_fill_main_seat():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config["projects"]["test"]["agents"] = ["claude"]
        app.proj_config = app.config["projects"]["test"]
        app.config["agent_fallbacks"] = {"claude": ["agent_zero"]}
        app.save_agent_statuses({"claude": {"status": "exhausted", "updated_at": app.timestamp()}})

        assert app.resolve_available_agents(["claude"], None) == []

        app.config["agents"]["agent_zero"]["can_fill_main_seat"] = True
        assert app.resolve_available_agents(["claude"], None) == ["agent_zero"]
        print("PASS: direct fallback must be allowed to fill a main seat")


def test_agent_zero_can_substitute_after_main_agents_exhausted_when_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config["agents"]["agent_zero"]["can_fill_main_seat"] = True
        app.save_agent_statuses(
            {
                "claude": {"status": "exhausted", "updated_at": app.timestamp()},
                "codex": {"status": "exhausted", "updated_at": app.timestamp()},
            }
        )
        app.run_agent_round = MagicMock()

        app.handle_user_input("please inspect this")

        app.run_agent_round.assert_called_once()
        _, kwargs = app.run_agent_round.call_args
        assert kwargs["agents"] == ["agent_zero"]
        transcript = app.chatboks_md.read_text(encoding="utf-8")
        assert "substituting agent_zero" in transcript
        print("PASS: Agent Zero can substitute after main agents are exhausted when allowed")


def test_explicit_route_to_exhausted_agent_does_not_substitute():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.save_agent_statuses({"claude": {"status": "exhausted", "updated_at": app.timestamp()}})
        app.run_agent_round = MagicMock()

        app.handle_user_input("@claude please inspect this")

        app.run_agent_round.assert_not_called()
        message = app.stream.system.call_args.args[0]
        assert "claude is exhausted" in message.lower()
        print("PASS: explicit exhausted route asks user to override")


if __name__ == "__main__":
    test_agent_command_marks_exhausted_without_agent_round()
    test_exhausted_command_accepts_duration_and_clock_time()
    test_expired_exhaustion_auto_clears_on_display()
    test_normal_round_substitutes_exhausted_agent()
    test_direct_fallback_must_be_allowed_to_fill_main_seat()
    test_agent_zero_can_substitute_after_main_agents_exhausted_when_allowed()
    test_explicit_route_to_exhausted_agent_does_not_substitute()
    print("\nAll agent status smoke tests passed.")
