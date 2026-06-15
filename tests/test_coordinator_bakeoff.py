from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "coordinator_bakeoff"
PLANNING_DOC = ROOT / "docs" / "planning" / "coordinator-model-bakeoff.md"
EXPECTED_IDS = {
    "route_remote_polish",
    "resume_after_sleep",
    "diagnose_pairing_failure",
    "classify_public_bridge_risk",
    "summarize_mobile_refresh_diff",
    "separate_agent_answer_from_system_noise",
    "replace_exhausted_claude_lane",
}
SCORING_DIMENSIONS = {
    "correctness",
    "brevity",
    "actionability",
    "boundary_awareness",
    "stability",
}
FORBIDDEN_CONTEXT_PATTERNS = [
    re.compile(r"bearer\s+[a-z0-9._-]+", re.IGNORECASE),
    re.compile(r"api[_ -]?key\s*[:=]", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*[a-z0-9._-]{12,}", re.IGNORECASE),
    re.compile(r"password\s*[:=]", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
]


def load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_coordinator_bakeoff_fixture_set_matches_plan() -> None:
    fixture_paths = sorted(FIXTURE_DIR.glob("*.json"))
    fixture_ids = {path.stem for path in fixture_paths}

    assert fixture_ids == EXPECTED_IDS

    planning_text = PLANNING_DOC.read_text(encoding="utf-8")
    for fixture_id in EXPECTED_IDS:
        assert fixture_id in planning_text


def test_coordinator_bakeoff_fixtures_are_valid_and_sanitized() -> None:
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        fixture = load_fixture(path)
        expected = fixture.get("expected")

        assert fixture["schema_version"] == 1
        assert fixture["id"] == path.stem
        assert fixture["id"] in EXPECTED_IDS
        assert isinstance(fixture["task"], str) and fixture["task"].strip()
        assert isinstance(fixture["context"], str) and 80 <= len(fixture["context"]) <= 1800
        assert isinstance(expected, dict)
        assert isinstance(expected["preferred_response_shape"], str)
        assert expected["preferred_response_shape"].strip()

        for field in ("must_include", "must_avoid", "scoring_focus"):
            values = expected[field]
            assert isinstance(values, list)
            assert 2 <= len(values) <= 5
            assert all(isinstance(value, str) and value.strip() for value in values)

        assert set(expected["scoring_focus"]).issubset(SCORING_DIMENSIONS)
        assert isinstance(fixture["tags"], list) and fixture["tags"]
        assert all(isinstance(tag, str) and tag.strip() for tag in fixture["tags"])

        context = fixture["context"]
        for pattern in FORBIDDEN_CONTEXT_PATTERNS:
            assert not pattern.search(context), f"{path.name} contains forbidden context pattern: {pattern.pattern}"


def test_coordinator_bakeoff_keeps_cloud_fallback_out_of_fixtures() -> None:
    combined_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    )

    assert "cloud fallback" not in combined_text
    assert "provider dashboard" not in combined_text
    assert "public exposure" in combined_text
