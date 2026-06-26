from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOL_LEDGER = ROOT / "docs" / "planning" / "tool-trust-ledger.md"
TRUST_CONTRACT = ROOT / "docs" / "planning" / "chatboks-trust-contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_tool_ledger_documents_attested_mcp_admission_controls() -> None:
    text = _read(TOOL_LEDGER)

    required_terms = [
        "mcp server admission policy",
        "deny-by-default",
        "admission state",
        "allowed toolset",
        "signed server assertion",
        "pinned trust root",
        "explicit user approval",
        "remote auth review",
        "oauth",
        "dynamic client registration",
        "callback",
        "host and session checks",
        "audit records",
        "no tool dispatch",
        "silent fallback",
    ]

    for term in required_terms:
        assert term in text


def test_trust_contract_denies_unadmitted_mcp_servers_by_default() -> None:
    text = _read(TRUST_CONTRACT)

    required_terms = [
        "mcp admission controls",
        "denied by default",
        "explicit admission state",
        "non-empty allowed toolset",
        "remote oauth review",
        "host-layer and session assumptions",
        "signed server assertions",
        "trust-boundary warnings",
        "must not silently reroute",
        "dynamic client registration",
        "callback",
        "blocks authenticated remote admission",
    ]

    for term in required_terms:
        assert term in text


def test_tool_ledger_documents_group_and_mutation_controls() -> None:
    text = _read(TOOL_LEDGER)

    required_terms = [
        "description-code consistency gate",
        "runtime metadata",
        "mismatch evidence",
        "tool-group and mutation gate",
        "group-level trust objects",
        "onboard related tools atomically",
        "mixed old/new tool states",
        "tool-surface mutations",
        "origin-bound registration identifiers",
        "multi-tool threshold behavior",
        "discovery-only inspection with no tool dispatch",
    ]

    for term in required_terms:
        assert term in text


def test_trust_contract_documents_protocol_readiness_controls() -> None:
    text = _read(TRUST_CONTRACT)

    required_terms = [
        "description-code consistency review",
        "tool-group and mutation review",
        "protocol readiness review",
        "runtime metadata",
        "mixed old/new high-risk tool groups",
        "origin-bound registration identifiers",
        "oauth mix-up prevention",
        "redirect/callback binding",
        "dpop",
        "workload identity federation",
        "sdk conformance",
        "fine-grained policy enforcement",
        "discovery-only",
    ]

    for term in required_terms:
        assert term in text
