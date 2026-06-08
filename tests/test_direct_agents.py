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


def test_role_route_uses_collaboration_mode_lane_when_configured():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "role_routes": {"implement": ["codex", "claude"]},
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
        router = Router(config, "chatboks", Path(tmp))

        agents, prompt, exclusive = router.route_user_prompt(
            "patch the timeout bug",
            collaboration_mode="implement",
        )

        assert agents == ["codex", "claude"]
        assert prompt == "patch the timeout bug"
        assert exclusive is None
        print("PASS: collaboration mode can select a role route")


def test_role_route_falls_back_to_default_round_when_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude"],
                    "role_routes": {"implement": ["codex", "claude"]},
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
        router = Router(config, "chatboks", Path(tmp))

        agents, _, exclusive = router.route_user_prompt(
            "ordinary request",
            collaboration_mode="default",
        )

        assert agents == ["claude"]
        assert exclusive is None
        print("PASS: unknown role route falls back to default round agents")


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


def test_explicit_route_ignores_collaboration_mode_lane():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "role_routes": {"implement": ["codex", "claude"]},
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
        router = Router(config, "chatboks", Path(tmp))

        agents, prompt, exclusive = router.route_user_prompt(
            "@claude review this",
            collaboration_mode="implement",
        )

        assert agents == ["claude"]
        assert prompt == "review this"
        assert exclusive == "claude"
        print("PASS: explicit route ignores role lane")


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


def test_agent_zero_diagnostic_fallback_uses_active_task_only():
    with tempfile.TemporaryDirectory() as tmp:
        agent = AgentZeroAgent(
            Path(tmp),
            {"cli": "ollama", "project_name": "chatboks"},
            "Agent Zero role",
        )
        prompt = (
            "[CHATBOKS RECENT - READ-ONLY PRIOR CONTEXT]\n"
            "Old turn: check this project setup and recommend the next diagnostic command.\n\n"
            "[ACTIVE TASK]\n"
            "summarize today's agenda in 5 bullets.\n\n"
            "[HANDOFF] None."
        )

        result = agent.fallback_for_bare_signal(prompt)

        assert "doctor.py" not in result
        assert "bare control signal" in result
        assert ">>> BLOCKED" in result
        print("PASS: Agent Zero fallback ignores stale diagnostic history")


def test_agent_zero_diagnostic_fallback_allows_current_setup_task():
    with tempfile.TemporaryDirectory() as tmp:
        agent = AgentZeroAgent(
            Path(tmp),
            {"cli": "ollama", "project_name": "chatboks"},
            "Agent Zero role",
        )
        prompt = (
            "[CHATBOKS RECENT - READ-ONLY PRIOR CONTEXT]\n"
            "Old turn: summarize routing policy.\n\n"
            "[ACTIVE TASK]\n"
            "check this project setup and recommend the next diagnostic command. Project: chatboks\n\n"
            "[HANDOFF] None."
        )

        result = agent.fallback_for_bare_signal(prompt)

        assert "python doctor.py chatboks" in result
        assert ">>> TASK_COMPLETE" in result
        print("PASS: Agent Zero fallback still handles current diagnostic tasks")


def test_agent_zero_routing_policy_fallback_uses_active_task():
    with tempfile.TemporaryDirectory() as tmp:
        agent = AgentZeroAgent(
            Path(tmp),
            {"cli": "ollama", "project_name": "chatboks"},
            "Agent Zero role",
        )
        prompt = (
            "[CHATBOKS RECENT - READ-ONLY PRIOR CONTEXT]\n"
            "Old turn: check this project setup and recommend the next diagnostic command.\n\n"
            "[ACTIVE TASK]\n"
            "summarize the current ChatBoks routing policy in 5 bullets.\n\n"
            "[HANDOFF] None."
        )

        result = agent.fallback_for_bare_signal(prompt)

        assert "doctor.py" not in result
        assert "@all opts into" in result
        assert "Direct routes" in result
        assert ">>> TASK_COMPLETE" in result
        print("PASS: Agent Zero fallback can summarize routing policy")


def test_routing_intelligence_can_auto_route_status_questions_to_agent_zero():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "routing_intelligence": {"enabled": True},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details("what's next for this project?")

        assert decision.agents == ["agent_zero"]
        assert decision.exclusive_agent is None
        assert decision.strategy == "agent_zero_direct"
        assert "Agent Zero" in (decision.note or "")
        print("PASS: routing intelligence can auto-route status checks to Agent Zero")


def test_routing_intelligence_can_auto_route_implementation_requests_to_codex():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "routing_intelligence": {"enabled": True},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details("implement provider fallback for codex timeouts")

        assert decision.agents == ["codex"]
        assert decision.exclusive_agent is None
        assert decision.strategy == "single_agent_codex"
        assert "Codex" in (decision.note or "")
        print("PASS: routing intelligence can auto-route implementation work to Codex")


def test_routing_intelligence_can_auto_route_architecture_review_to_claude():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "routing_intelligence": {"enabled": True},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details("review the architecture for token recovery")

        assert decision.agents == ["claude"]
        assert decision.exclusive_agent is None
        assert decision.strategy == "single_agent_claude"
        assert "Claude" in (decision.note or "")
        print("PASS: routing intelligence can auto-route architecture review to Claude")


def test_routing_intelligence_defers_to_full_round_for_brainstorm_requests():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "routing_intelligence": {"enabled": True},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details(
            "brainstorm three options for future routing policy",
            collaboration_mode="brainstorm",
        )

        assert decision.agents == ["claude", "codex"]
        assert decision.exclusive_agent is None
        assert decision.strategy == "full_round"
        assert decision.note is None
        print("PASS: routing intelligence keeps brainstorm prompts in the full round")


def test_mode_strategy_can_route_implement_mode_to_codex_solo():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "mode_strategies": {"implement": "solo_codex"},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details(
            "continue with the next patch",
            collaboration_mode="implement",
        )

        assert decision.agents == ["codex"]
        assert decision.exclusive_agent is None
        assert decision.strategy == "mode_solo_codex"
        assert "Codex" in (decision.note or "")
        print("PASS: implement mode can route to Codex solo")


def test_mode_strategy_can_route_review_mode_to_claude_solo():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "mode_strategies": {"review": "solo_claude"},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details(
            "look for the biggest risk in this diff",
            collaboration_mode="review",
        )

        assert decision.agents == ["claude"]
        assert decision.exclusive_agent is None
        assert decision.strategy == "mode_solo_claude"
        assert "Claude" in (decision.note or "")
        print("PASS: review mode can route to Claude solo")


def test_mode_strategy_still_allows_agent_zero_for_lightweight_diagnose_requests():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "routing_intelligence": {"enabled": True},
                    "mode_strategies": {"diagnose": "solo_claude"},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details(
            "what's next for this project?",
            collaboration_mode="diagnose",
        )

        assert decision.agents == ["agent_zero"]
        assert decision.strategy == "agent_zero_direct"
        print("PASS: Agent Zero can still catch lightweight diagnose requests")


def test_explicit_route_still_overrides_mode_strategy():
    with tempfile.TemporaryDirectory() as tmp:
        config = {
            "projects": {
                "chatboks": {
                    "path": str(Path(tmp)),
                    "agents": ["claude", "codex"],
                    "round_agents": ["claude", "codex"],
                    "direct_agents": ["agent_zero"],
                    "mode_strategies": {"review": "solo_claude"},
                    "primary": "codex",
                }
            },
            "agents": {
                "agent_zero": {},
                "claude": {},
                "codex": {},
            },
        }
        router = Router(config, "chatboks", Path(tmp))

        decision = router.route_user_prompt_details(
            "@codex review this patch",
            collaboration_mode="review",
        )

        assert decision.agents == ["codex"]
        assert decision.exclusive_agent == "codex"
        assert decision.strategy == "explicit_agent"
        print("PASS: explicit routes still override mode strategies")


if __name__ == "__main__":
    test_normal_route_excludes_direct_agent()
    test_normal_route_uses_default_round_agents_when_configured()
    test_role_route_uses_collaboration_mode_lane_when_configured()
    test_role_route_falls_back_to_default_round_when_unknown()
    test_all_route_opts_into_full_project_team_not_direct_agents()
    test_explicit_route_ignores_collaboration_mode_lane()
    test_agent_zero_direct_route_aliases_work()
    test_unlisted_agent_direct_route_falls_back_to_normal_round()
    test_agent_zero_call_accepts_base_timeout_keywords()
    test_agent_zero_diagnostic_fallback_uses_active_task_only()
    test_agent_zero_diagnostic_fallback_allows_current_setup_task()
    test_agent_zero_routing_policy_fallback_uses_active_task()
    test_routing_intelligence_can_auto_route_status_questions_to_agent_zero()
    test_routing_intelligence_can_auto_route_implementation_requests_to_codex()
    test_routing_intelligence_can_auto_route_architecture_review_to_claude()
    test_routing_intelligence_defers_to_full_round_for_brainstorm_requests()
    test_mode_strategy_can_route_implement_mode_to_codex_solo()
    test_mode_strategy_can_route_review_mode_to_claude_solo()
    test_mode_strategy_still_allows_agent_zero_for_lightweight_diagnose_requests()
    test_explicit_route_still_overrides_mode_strategy()
    print("\nAll direct-agent smoke tests passed.")
