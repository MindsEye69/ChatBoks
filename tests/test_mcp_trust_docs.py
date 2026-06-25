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
