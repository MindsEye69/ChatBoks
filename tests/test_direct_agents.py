"""Smoke tests for agents that are available only through explicit @routes."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent_zero import AgentZeroAgent
from router import Router


def _make_router(root: Path) -> Router:
    config = {
        "projects": {
            "chatboks": {
                "path": str(root),
                "agents": ["claude", "codex"],
                "direct_agents": ["agent_zero"],
                "primary": "codex",
            }
        },
        "agents": {
            "agent_zero": {},
            "claude": {},
            "codex": {},
        },
    }
    return Router(config, "chatboks", root)


def test_normal_route_excludes_direct_agent():
    with tempfile.TemporaryDirectory() as tmp:
        router = _make_router(Path(tmp))

        agents, prompt, exclusive = router.route_user_prompt("review this")

        assert agents == ["claude", "codex"]
        assert prompt == "review this"
        assert exclusive is None
        print("PASS: normal route excludes direct-only agent")


def test_normal_route_uses_default_round_agents_when_configured():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex", "antigravity"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
                "antigravity": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        agents, prompt, exclusive = router.route_user_prompt("review this")

        assert agents == ["claude", "codex"]
        assert prompt == "review this"
        assert exclusive is None
        print("PASS: normal route can be limited to default round agents")


def test_all_route_opts_into_full_project_team_not_direct_agents():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex", "antigravity"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
                "antigravity": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        agents, prompt, exclusive = router.route_user_prompt("@all compare options")

        assert agents == ["claude", "codex", "antigravity"]
        assert "agent_zero" not in agents
        assert prompt == "compare options"
        assert exclusive is None
        print("PASS: @all opts into the full non-direct project team")


def test_agent_zero_direct_route_aliases_work():
    with tempfile.TemporaryDirectory() as tmp:
        router = _make_router(Path(tmp))

        for alias in ("@zero", "@agent0", "@0", "@forge", "@az"):
            agents, prompt, exclusive = router.route_user_prompt(f"{alias} check setup")
            assert agents == ["agent_zero"]
            assert prompt == "check setup"
            assert exclusive == "agent_zero"

        print("PASS: Agent Zero direct route aliases work")


def test_unlisted_agent_direct_route_falls_back_to_normal_round():
    with tempfile.TemporaryDirectory() as tmp:
        router = _make_router(Path(tmp))

        agents, prompt, exclusive = router.route_user_prompt("@antigravity check setup")

        assert agents == ["claude", "codex"]
        assert prompt == "@antigravity check setup"
        assert exclusive is None
        print("PASS: unlisted direct route falls back to normal round")


def test_agent_zero_call_accepts_base_timeout_keywords():
    with tempfile.TemporaryDirectory() as tmp:
        agent = AgentZeroAgent(
            Path(tmp),
            {
                "cli": "ollama",
                "endpoint": "http://127.0.0.1:11434/api/chat",
                "model": "test",
                "project_name": "chatboks",
            },
            "Agent Zero role",
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"message":{"content":"Ready.\\n>>> TASK_COMPLETE"}}'

        with patch("agents.agent_zero.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            result = agent.call("compact context")

        assert "Ready." in result
        assert ">>> TASK_COMPLETE" in result
        assert urlopen.call_args.kwargs["timeout"] == 900
        print("PASS: Agent Zero call accepts BaseAgent timeout keywords")


if __name__ == "__main__":
    test_normal_route_excludes_direct_agent()
    test_normal_route_uses_default_round_agents_when_configured()
    test_all_route_opts_into_full_project_team_not_direct_agents()
    test_agent_zero_direct_route_aliases_work()
    test_unlisted_agent_direct_route_falls_back_to_normal_round()
    test_agent_zero_call_accepts_base_timeout_keywords()
    print("\nAll direct-agent smoke tests passed.")
