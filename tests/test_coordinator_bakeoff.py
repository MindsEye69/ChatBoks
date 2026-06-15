from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import coordinator_bakeoff

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


def test_coordinator_bakeoff_runner_dry_run_does_not_call_ollama(capsys) -> None:
    with patch("sys.argv", ["coordinator_bakeoff.py", "--fixture", "route_remote_polish"]):
        with patch("urllib.request.urlopen") as mock_open:
            exit_code = coordinator_bakeoff.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dry run only" in captured.out
    assert "route_remote_polish" in captured.out
    mock_open.assert_not_called()


def test_coordinator_bakeoff_runner_refuses_non_loopback_endpoint(capsys) -> None:
    with patch(
        "sys.argv",
        [
            "coordinator_bakeoff.py",
            "--run",
            "--endpoint",
            "https://example.com/api/chat",
            "--fixture",
            "route_remote_polish",
        ],
    ):
        with patch("urllib.request.urlopen") as mock_open:
            exit_code = coordinator_bakeoff.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Refusing non-loopback endpoint" in captured.out
    mock_open.assert_not_called()


def test_coordinator_bakeoff_runner_writes_mocked_result(tmp_path: Path) -> None:
    response = MagicMock()
    response.readline.side_effect = [
        b'{"message":{"content":"Route to Codex."},"done":false}\n',
        b'{"message":{"content":" >>> TASK_COMPLETE"},"done":true}\n',
        b"",
    ]
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)

    with patch(
        "sys.argv",
        [
            "coordinator_bakeoff.py",
            "--run",
            "--fixture",
            "route_remote_polish",
            "--model",
            "mock-model",
            "--output-dir",
            str(tmp_path),
        ],
    ):
        with patch("urllib.request.urlopen", return_value=response):
            exit_code = coordinator_bakeoff.main()

    assert exit_code == 0
    result_files = list(tmp_path.glob("*-mock-model.jsonl"))
    assert len(result_files) == 1
    records = [json.loads(line) for line in result_files[0].read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["fixture_id"] == "route_remote_polish"
    assert records[0]["model"] == "mock-model"
    assert records[0]["output"] == "Route to Codex. >>> TASK_COMPLETE"
    assert records[0]["error"] == ""
    assert "must_include" in records[0]["expected"]


def test_coordinator_bakeoff_prompt_does_not_leak_expected_hints() -> None:
    fixture = load_fixture(FIXTURE_DIR / "route_remote_polish.json")
    prompt = coordinator_bakeoff.build_prompt(fixture)

    assert "must_include" not in prompt
    assert "must_avoid" not in prompt
    assert "scoring" not in prompt.lower()
    assert fixture["task"] in prompt
    assert fixture["context"] in prompt
