"""Dedicated unit tests for Router and RoutingDecision."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from router import Router, RoutingDecision


# ---------------------------------------------------------------------------
# Config/Router helpers
# ---------------------------------------------------------------------------

def _config(
    *agents: str,
    primary: str | None = None,
    role_routes: dict | None = None,
    mode_strategies: dict | None = None,
    direct_agents: list[str] | None = None,
    round_agents: list[str] | None = None,
    default_agents: list[str] | None = None,
    routing_intelligence: bool = False,
) -> dict:
    proj: dict = {"agents": list(agents)}
    if primary is not None:
        proj["primary"] = primary
    if role_routes is not None:
        proj["role_routes"] = role_routes
    if mode_strategies is not None:
        proj["mode_strategies"] = mode_strategies
    if direct_agents is not None:
        proj["direct_agents"] = direct_agents
    if round_agents is not None:
        proj["round_agents"] = round_agents
    if default_agents is not None:
        proj["default_agents"] = default_agents
    if routing_intelligence:
        proj["routing_intelligence"] = {"enabled": True}
    all_names = list(agents) + (direct_agents or [])
    return {
        "projects": {"test": proj},
        "agents": {n: {} for n in all_names},
    }


def _router(*agents: str, **kwargs) -> Router:
    return Router(_config(*agents, **kwargs), "test", Path("."))


# ---------------------------------------------------------------------------
# RoutingDecision dataclass
# ---------------------------------------------------------------------------

def test_routing_decision_defaults():
    d = RoutingDecision(["claude"], "hello")
    assert d.agents == ["claude"]
    assert d.cleaned_prompt == "hello"
    assert d.exclusive_agent is None
    assert d.note is None
    assert d.strategy == "full_round"
    print("PASS: RoutingDecision default fields")


def test_routing_decision_is_frozen():
    d = RoutingDecision(["claude"], "hello")
    try:
        d.strategy = "other"  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:
        assert False, "Should have raised FrozenInstanceError"
    print("PASS: RoutingDecision is immutable")


def test_routing_decision_explicit_fields():
    d = RoutingDecision(["codex"], "fix it", "codex", "note text", "explicit_agent")
    assert d.exclusive_agent == "codex"
    assert d.note == "note text"
    assert d.strategy == "explicit_agent"
    print("PASS: RoutingDecision accepts explicit field values")


# ---------------------------------------------------------------------------
# Router.primary
# ---------------------------------------------------------------------------

def test_primary_returns_configured_primary():
    r = _router("claude", "codex", primary="codex")
    assert r.primary() == "codex"
    print("PASS: primary returns configured value when valid")


def test_primary_falls_back_to_first_agent_when_unconfigured():
    r = _router("claude", "codex")
    assert r.primary() == "claude"
    print("PASS: primary falls back to first agent")


def test_primary_falls_back_when_configured_primary_not_in_agents():
    r = _router("claude", "codex", primary="antigravity")
    assert r.primary() == "claude"
    print("PASS: primary falls back when configured value is not a project agent")


# ---------------------------------------------------------------------------
# Router.after
# ---------------------------------------------------------------------------

def test_after_returns_next_agent():
    r = _router("claude", "codex", "coordinator")
    assert r.after("claude") == "codex"
    assert r.after("codex") == "coordinator"
    print("PASS: after returns next agent in sequence")


def test_after_returns_you_at_end_of_list():
    r = _router("claude", "codex")
    assert r.after("codex") == "you"
    print("PASS: after returns 'you' at end of agent list")


def test_after_unknown_agent_returns_primary():
    r = _router("claude", "codex")
    assert r.after("unknown") == "claude"
    print("PASS: after returns primary for unknown agent")


# ---------------------------------------------------------------------------
# Router.normalize_round_agents
# ---------------------------------------------------------------------------

def test_normalize_round_agents_filters_nonmembers():
    r = _router("claude", "codex")
    assert r.normalize_round_agents(["claude", "coordinator"]) == ["claude"]
    print("PASS: normalize filters agents not in project")


def test_normalize_round_agents_deduplicates():
    r = _router("claude", "codex")
    assert r.normalize_round_agents(["codex", "codex", "claude"]) == ["codex", "claude"]
    print("PASS: normalize deduplicates entries")


def test_normalize_round_agents_non_list_returns_empty():
    r = _router("claude", "codex")
    assert r.normalize_round_agents(None) == []
    assert r.normalize_round_agents("codex") == []
    print("PASS: normalize returns empty list for non-list input")


def test_normalize_round_agents_preserves_order():
    r = _router("claude", "codex", "coordinator")
    assert r.normalize_round_agents(["codex", "claude"]) == ["codex", "claude"]
    print("PASS: normalize preserves insertion order")


# ---------------------------------------------------------------------------
# Router.normal_round_agents
# ---------------------------------------------------------------------------

def test_normal_round_agents_uses_role_routes():
    r = _router("claude", "codex", role_routes={"implement": ["codex"]})
    assert r.normal_round_agents("implement") == ["codex"]
    print("PASS: normal_round_agents uses role_routes")


def test_normal_round_agents_falls_back_when_no_role_route():
    r = _router("claude", "codex")
    assert r.normal_round_agents("implement") == ["claude", "codex"]
    print("PASS: normal_round_agents falls back to all agents when no role route")


def test_normal_round_agents_no_mode_returns_all_agents():
    r = _router("claude", "codex")
    assert r.normal_round_agents(None) == ["claude", "codex"]
    print("PASS: normal_round_agents returns all agents when mode is None")


def test_normal_round_agents_uses_round_agents_config():
    r = _router("claude", "codex", "coordinator", round_agents=["codex", "claude"])
    assert r.normal_round_agents(None) == ["codex", "claude"]
    print("PASS: normal_round_agents uses configured round_agents")


def test_normal_round_agents_uses_default_agents_when_no_round_agents():
    r = _router("claude", "codex", "coordinator", default_agents=["coordinator", "claude"])
    assert r.normal_round_agents(None) == ["coordinator", "claude"]
    print("PASS: normal_round_agents uses default_agents fallback")


# ---------------------------------------------------------------------------
# Router.route_user_prompt_details — no @-prefix
# ---------------------------------------------------------------------------

def test_route_no_prefix_returns_all_agents():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("explain this")
    assert d.agents == ["claude", "codex"]
    assert d.cleaned_prompt == "explain this"
    assert d.exclusive_agent is None
    print("PASS: no-prefix prompt routes to all agents")


def test_route_no_prefix_preserves_original_text():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("  explain this")
    assert d.cleaned_prompt == "  explain this"
    print("PASS: no-prefix prompt preserves original text including leading space")


# ---------------------------------------------------------------------------
# Router.route_user_prompt_details — @all / @team / @everyone
# ---------------------------------------------------------------------------

def test_route_at_all_routes_to_all_agents():
    r = _router("claude", "codex", "coordinator")
    d = r.route_user_prompt_details("@all review this")
    assert set(d.agents) == {"claude", "codex", "coordinator"}
    assert d.cleaned_prompt == "review this"
    assert d.strategy == "explicit_all"
    print("PASS: @all routes to every project agent")


def test_route_at_team_routes_to_all_agents():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@team review this")
    assert d.agents == ["claude", "codex"]
    assert d.strategy == "explicit_all"
    print("PASS: @team routes to every project agent")


def test_route_at_everyone_routes_to_all_agents():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@everyone review this")
    assert d.agents == ["claude", "codex"]
    assert d.strategy == "explicit_all"
    print("PASS: @everyone routes to every project agent")


def test_route_at_all_no_body_falls_back_to_full_text():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@all")
    assert d.cleaned_prompt == "@all"
    print("PASS: @all with no body falls back to original text")


# ---------------------------------------------------------------------------
# Router.route_user_prompt_details — @agent exclusive
# ---------------------------------------------------------------------------

def test_route_at_codex_exclusive():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@codex fix the bug")
    assert d.agents == ["codex"]
    assert d.exclusive_agent == "codex"
    assert d.cleaned_prompt == "fix the bug"
    assert d.strategy == "explicit_agent"
    print("PASS: @codex routes exclusively to codex")


def test_route_at_claude_exclusive():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@claude review this")
    assert d.agents == ["claude"]
    assert d.exclusive_agent == "claude"
    assert d.strategy == "explicit_agent"
    print("PASS: @claude routes exclusively to claude")


def test_route_at_direct_agent_exclusive():
    r = _router("claude", "codex", direct_agents=["coordinator"])
    d = r.route_user_prompt_details("@coordinator check status")
    assert d.agents == ["coordinator"]
    assert d.exclusive_agent == "coordinator"
    assert d.cleaned_prompt == "check status"
    assert d.strategy == "explicit_agent"
    print("PASS: @agent can route to configured direct agent")


def test_route_at_agent_no_body_uses_full_text():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@codex")
    assert d.agents == ["codex"]
    assert d.cleaned_prompt == "@codex"
    print("PASS: @agent with no body falls back to original text")


# ---------------------------------------------------------------------------
# Router.route_user_prompt_details — alias resolution
# ---------------------------------------------------------------------------

def test_route_alias_spark_maps_to_codex_spark():
    r = _router("claude", "codex", "codex_spark")
    d = r.route_user_prompt_details("@spark do something")
    assert d.agents == ["codex_spark"]
    assert d.exclusive_agent == "codex_spark"
    print("PASS: @spark alias resolves to codex_spark")


def test_route_alias_coord_maps_to_coordinator():
    r = _router("claude", "codex", "coordinator")
    d = r.route_user_prompt_details("@coord do something")
    assert d.agents == ["coordinator"]
    assert d.exclusive_agent == "coordinator"
    print("PASS: @coord alias resolves to coordinator")


def test_route_alias_antigrav_maps_to_antigravity():
    r = _router("claude", "codex", "antigravity")
    d = r.route_user_prompt_details("@antigrav do something")
    assert d.agents == ["antigravity"]
    assert d.exclusive_agent == "antigravity"
    print("PASS: @antigrav alias resolves to antigravity")


def test_route_alias_agy_maps_to_antigravity():
    r = _router("claude", "codex", "antigravity")
    d = r.route_user_prompt_details("@agy do something")
    assert d.agents == ["antigravity"]
    print("PASS: @agy alias resolves to antigravity")


def test_route_alias_codexspark_maps_to_codex_spark():
    r = _router("claude", "codex", "codex_spark")
    d = r.route_user_prompt_details("@codexspark do something")
    assert d.agents == ["codex_spark"]
    assert d.exclusive_agent == "codex_spark"
    print("PASS: @codexspark alias resolves to codex_spark")


# ---------------------------------------------------------------------------
# Router.route_user_prompt_details — unknown @agent falls back to round
# ---------------------------------------------------------------------------

def test_route_at_unknown_agent_falls_back_to_round():
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@nonexistent do something")
    assert d.agents == ["claude", "codex"]
    assert d.exclusive_agent is None
    print("PASS: @unknown_agent falls back to normal round")


def test_route_at_agent_not_in_project_falls_back_to_round():
    # coordinator is a known AGENT_CLASS but is not in this project's agents list
    r = _router("claude", "codex")
    d = r.route_user_prompt_details("@coordinator do something")
    assert d.agents == ["claude", "codex"]
    assert d.exclusive_agent is None
    print("PASS: @agent not in project falls back to normal round")


# ---------------------------------------------------------------------------
# Router.route_mode_strategy
# ---------------------------------------------------------------------------

def test_route_mode_strategy_no_mode_returns_none():
    r = _router("claude", "codex", mode_strategies={"review": "solo_claude"})
    assert r.route_mode_strategy("explain", None) is None
    assert r.route_mode_strategy("explain", "") is None
    print("PASS: route_mode_strategy returns None when no mode set")


def test_route_mode_strategy_solo_codex():
    r = _router("claude", "codex", mode_strategies={"implement": "solo_codex"})
    d = r.route_mode_strategy("do it", "implement")
    assert d is not None
    assert d.agents == ["codex"]
    assert d.strategy == "mode_solo_codex"
    assert "implement" in (d.note or "")
    print("PASS: solo_codex strategy routes to codex")


def test_route_mode_strategy_solo_codex_without_codex_returns_none():
    r = _router("claude", mode_strategies={"implement": "solo_codex"})
    assert r.route_mode_strategy("do it", "implement") is None
    print("PASS: solo_codex returns None when codex is not a project agent")


def test_route_mode_strategy_solo_claude():
    r = _router("claude", "codex", mode_strategies={"review": "solo_claude"})
    d = r.route_mode_strategy("review this", "review")
    assert d is not None
    assert d.agents == ["claude"]
    assert d.strategy == "mode_solo_claude"
    assert "review" in (d.note or "")
    print("PASS: solo_claude strategy routes to claude")


def test_route_mode_strategy_solo_claude_without_claude_returns_none():
    r = _router("codex", mode_strategies={"review": "solo_claude"})
    assert r.route_mode_strategy("review this", "review") is None
    print("PASS: solo_claude returns None when claude is not a project agent")


def test_route_mode_strategy_full_round():
    r = _router("claude", "codex", mode_strategies={"brainstorm": "full_round"})
    d = r.route_mode_strategy("ideas?", "brainstorm")
    assert d is not None
    assert d.agents == ["claude", "codex"]
    print("PASS: full_round strategy routes to all agents")


def test_route_mode_strategy_confirm_round():
    r = _router("claude", "codex", primary="codex", mode_strategies={"confirmation": "confirm_round"})
    d = r.route_mode_strategy("implement it", "confirmation")
    assert d is not None
    assert d.agents == ["codex"]
    assert d.strategy == "mode_confirmation"
    assert "confirmation" in (d.note or "").lower()
    print("PASS: confirm_round routes to primary agent")


def test_route_mode_strategy_unknown_strategy_returns_none():
    r = _router("claude", "codex", mode_strategies={"custom": "whatever"})
    assert r.route_mode_strategy("do it", "custom") is None
    print("PASS: unknown mode strategy value returns None")


def test_route_mode_strategy_unlisted_mode_returns_none():
    r = _router("claude", "codex", mode_strategies={"implement": "solo_codex"})
    assert r.route_mode_strategy("do it", "brainstorm") is None
    print("PASS: mode without configured strategy returns None")


# ---------------------------------------------------------------------------
# Router.route_mode_strategy — role_routes vs mode_strategies interaction
# ---------------------------------------------------------------------------

def test_full_round_strategy_respects_role_routes():
    r = _router(
        "claude", "codex",
        role_routes={"brainstorm": ["claude"]},
        mode_strategies={"brainstorm": "full_round"},
    )
    d = r.route_mode_strategy("ideas?", "brainstorm")
    assert d is not None
    # full_round calls normal_round_agents which uses role_routes
    assert d.agents == ["claude"]
    print("PASS: full_round strategy respects role_routes override")


# ---------------------------------------------------------------------------
# Router.auto_route_prompt — routing intelligence
# ---------------------------------------------------------------------------

def test_auto_route_disabled_returns_none():
    r = _router("claude", "codex")
    assert r.auto_route_prompt("implement something", None) is None
    print("PASS: auto_route returns None when routing_intelligence disabled")


def test_auto_route_codex_for_implementation_prompt():
    r = _router("claude", "codex", routing_intelligence=True)
    d = r.auto_route_prompt("implement the new feature", None)
    assert d is not None
    assert d.agents == ["codex"]
    assert d.strategy == "single_agent_codex"
    print("PASS: routing intelligence routes implementation prompts to codex")


def test_auto_route_claude_for_analysis_prompt():
    r = _router("claude", "codex", routing_intelligence=True)
    d = r.auto_route_prompt("explain how the auth flow works", None)
    assert d is not None
    assert d.agents == ["claude"]
    assert d.strategy == "single_agent_claude"
    print("PASS: routing intelligence routes analysis prompts to claude")


def test_auto_route_empty_prompt_returns_none():
    r = _router("claude", "codex", routing_intelligence=True)
    assert r.auto_route_prompt("", None) is None
    assert r.auto_route_prompt("   ", None) is None
    print("PASS: auto_route returns None for empty prompt")


def test_auto_route_codex_suppressed_in_brainstorm_mode():
    r = _router("claude", "codex", routing_intelligence=True)
    d = r.auto_route_prompt("implement the feature", "brainstorm")
    assert d is None or d.strategy != "single_agent_codex"
    print("PASS: auto_route does not route to codex in brainstorm mode")


def test_auto_route_codex_suppressed_for_tradeoff_prompts():
    r = _router("claude", "codex", routing_intelligence=True)
    d = r.auto_route_prompt("implement and compare tradeoffs", None)
    assert d is None or d.strategy != "single_agent_codex"
    print("PASS: auto_route does not route to codex when prompt asks for tradeoffs")


def test_auto_route_claude_suppressed_when_prompt_contains_implement():
    r = _router("claude", "codex", routing_intelligence=True)
    d = r.auto_route_prompt("implement and explain how it works", None)
    assert d is None or d.strategy != "single_agent_claude"
    print("PASS: auto_route does not route to claude when prompt contains 'implement'")


# ---------------------------------------------------------------------------
# Router.route_user_prompt — tuple return
# ---------------------------------------------------------------------------

def test_route_user_prompt_returns_tuple():
    r = _router("claude", "codex")
    agents, cleaned, exclusive = r.route_user_prompt("@codex fix this")
    assert agents == ["codex"]
    assert cleaned == "fix this"
    assert exclusive == "codex"
    print("PASS: route_user_prompt returns (agents, cleaned_prompt, exclusive_agent)")


def test_route_user_prompt_no_exclusive_is_none():
    r = _router("claude", "codex")
    agents, cleaned, exclusive = r.route_user_prompt("review this")
    assert exclusive is None
    print("PASS: route_user_prompt returns None exclusive for non-exclusive routing")


# ---------------------------------------------------------------------------
# Router.__init__ — normalization edge cases
# ---------------------------------------------------------------------------

def test_router_normalizes_role_routes_keys_lowercase():
    r = _router("claude", "codex", role_routes={"IMPLEMENT": ["codex"]})
    assert "implement" in r.role_routes
    assert r.normal_round_agents("implement") == ["codex"]
    print("PASS: role_routes keys are normalized to lowercase")


def test_router_normalizes_mode_strategies_keys_lowercase():
    r = _router("claude", "codex", mode_strategies={"REVIEW": "solo_claude"})
    assert "review" in r.mode_strategies
    print("PASS: mode_strategies keys are normalized to lowercase")


def test_router_normalizes_mode_strategy_values_lowercase():
    r = _router("claude", "codex", mode_strategies={"review": " SOLO_CLAUDE "})
    d = r.route_mode_strategy("review this", "review")
    assert d is not None
    assert d.agents == ["claude"]
    assert d.strategy == "mode_solo_claude"
    print("PASS: mode_strategy values are stripped and lowercased")


def test_router_routing_intelligence_disabled_by_default():
    r = _router("claude", "codex")
    assert not r.routing_intelligence_enabled
    print("PASS: routing_intelligence is disabled by default")


def test_router_routing_intelligence_enabled_when_configured():
    r = _router("claude", "codex", routing_intelligence=True)
    assert r.routing_intelligence_enabled
    print("PASS: routing_intelligence enabled when configured")


def test_router_empty_mode_strategies_entry_ignored():
    # An empty-string key in mode_strategies must not pollute the dict
    config = _config("claude", "codex")
    config["projects"]["test"]["mode_strategies"] = {"": "solo_codex", "review": "solo_claude"}
    r = Router(config, "test", Path("."))
    assert "" not in r.mode_strategies
    assert "review" in r.mode_strategies
    print("PASS: empty-string mode_strategies keys are dropped on init")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_routing_decision_defaults()
    test_routing_decision_is_frozen()
    test_routing_decision_explicit_fields()
    test_primary_returns_configured_primary()
    test_primary_falls_back_to_first_agent_when_unconfigured()
    test_primary_falls_back_when_configured_primary_not_in_agents()
    test_after_returns_next_agent()
    test_after_returns_you_at_end_of_list()
    test_after_unknown_agent_returns_primary()
    test_normalize_round_agents_filters_nonmembers()
    test_normalize_round_agents_deduplicates()
    test_normalize_round_agents_non_list_returns_empty()
    test_normalize_round_agents_preserves_order()
    test_normal_round_agents_uses_role_routes()
    test_normal_round_agents_falls_back_when_no_role_route()
    test_normal_round_agents_no_mode_returns_all_agents()
    test_normal_round_agents_uses_round_agents_config()
    test_normal_round_agents_uses_default_agents_when_no_round_agents()
    test_route_no_prefix_returns_all_agents()
    test_route_no_prefix_preserves_original_text()
    test_route_at_all_routes_to_all_agents()
    test_route_at_team_routes_to_all_agents()
    test_route_at_everyone_routes_to_all_agents()
    test_route_at_all_no_body_falls_back_to_full_text()
    test_route_at_codex_exclusive()
    test_route_at_claude_exclusive()
    test_route_at_direct_agent_exclusive()
    test_route_at_agent_no_body_uses_full_text()
    test_route_alias_spark_maps_to_codex_spark()
    test_route_alias_coord_maps_to_coordinator()
    test_route_alias_antigrav_maps_to_antigravity()
    test_route_alias_agy_maps_to_antigravity()
    test_route_alias_codexspark_maps_to_codex_spark()
    test_route_at_unknown_agent_falls_back_to_round()
    test_route_at_agent_not_in_project_falls_back_to_round()
    test_route_mode_strategy_no_mode_returns_none()
    test_route_mode_strategy_solo_codex()
    test_route_mode_strategy_solo_codex_without_codex_returns_none()
    test_route_mode_strategy_solo_claude()
    test_route_mode_strategy_solo_claude_without_claude_returns_none()
    test_route_mode_strategy_full_round()
    test_route_mode_strategy_confirm_round()
    test_route_mode_strategy_unknown_strategy_returns_none()
    test_route_mode_strategy_unlisted_mode_returns_none()
    test_full_round_strategy_respects_role_routes()
    test_auto_route_disabled_returns_none()
    test_auto_route_codex_for_implementation_prompt()
    test_auto_route_claude_for_analysis_prompt()
    test_auto_route_empty_prompt_returns_none()
    test_auto_route_codex_suppressed_in_brainstorm_mode()
    test_auto_route_codex_suppressed_for_tradeoff_prompts()
    test_auto_route_claude_suppressed_when_prompt_contains_implement()
    test_route_user_prompt_returns_tuple()
    test_route_user_prompt_no_exclusive_is_none()
    test_router_normalizes_role_routes_keys_lowercase()
    test_router_normalizes_mode_strategies_keys_lowercase()
    test_router_normalizes_mode_strategy_values_lowercase()
    test_router_routing_intelligence_disabled_by_default()
    test_router_routing_intelligence_enabled_when_configured()
    test_router_empty_mode_strategies_entry_ignored()
    print("\nAll router unit tests passed.")
