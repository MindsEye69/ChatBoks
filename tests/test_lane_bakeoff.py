from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import lane_bakeoff

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "lane_bakeoff"
EXPECTED_IDS = {
    "architecture_byom_lane_runtime",
    "refactor_openai_compat_agent",
    "critique_confirmation_packet",
    "long_context_synthesis",
    "protocol_signal_compliance",
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


def test_lane_bakeoff_fixture_set_is_expected() -> None:
    fixture_paths = sorted(FIXTURE_DIR.glob("*.json"))
    fixture_ids = {path.stem for path in fixture_paths}

    assert fixture_ids == EXPECTED_IDS


def test_lane_bakeoff_fixtures_are_valid_and_sanitized() -> None:
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        fixture = load_fixture(path)
        expected = fixture.get("expected")

        assert fixture["schema_version"] == 1
        assert fixture["id"] == path.stem
        assert fixture["id"] in EXPECTED_IDS
        assert isinstance(fixture["task"], str) and fixture["task"].strip()
        assert isinstance(fixture["context"], str) and 120 <= len(fixture["context"]) <= 2200
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


def test_lane_bakeoff_runner_dry_run_does_not_call_api(capsys) -> None:
    with patch("sys.argv", ["lane_bakeoff.py", "--fixture", "architecture_byom_lane_runtime"]):
        with patch("urllib.request.urlopen") as mock_open:
            exit_code = lane_bakeoff.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dry run only" in captured.out
    assert "architecture_byom_lane_runtime" in captured.out
    mock_open.assert_not_called()


def test_lane_bakeoff_runner_refuses_missing_api_key(capsys) -> None:
    with patch.dict("os.environ", {}, clear=True):
        with patch(
            "sys.argv",
            [
                "lane_bakeoff.py",
                "--run",
                "--fixture",
                "architecture_byom_lane_runtime",
            ],
        ):
            with patch("urllib.request.urlopen") as mock_open:
                exit_code = lane_bakeoff.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Missing API key environment variable: ZAI_API_KEY" in captured.out
    mock_open.assert_not_called()


def test_lane_bakeoff_runner_writes_mocked_result(tmp_path: Path) -> None:
    response = MagicMock()
    response.read.return_value = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": "Keep GLM-5.2 as an optional lane preset.\n>>> TASK_COMPLETE"
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }
    ).encode("utf-8")
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)

    with patch.dict("os.environ", {"ZAI_API_KEY": "test-key"}, clear=True):
        with patch(
            "sys.argv",
            [
                "lane_bakeoff.py",
                "--run",
                "--fixture",
                "architecture_byom_lane_runtime",
                "--model",
                "mock-glm",
                "--output-dir",
                str(tmp_path),
            ],
        ):
            with patch("urllib.request.urlopen", return_value=response):
                exit_code = lane_bakeoff.main()

    assert exit_code == 0
    result_files = list(tmp_path.glob("*-mock-glm.jsonl"))
    assert len(result_files) == 1
    records = [json.loads(line) for line in result_files[0].read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["fixture_id"] == "architecture_byom_lane_runtime"
    assert records[0]["model"] == "mock-glm"
    assert records[0]["provider"] == "openai_compat"
    assert records[0]["output"] == "Keep GLM-5.2 as an optional lane preset.\n>>> TASK_COMPLETE"
    assert records[0]["usage"]["prompt_tokens"] == 10
    assert records[0]["error"] == ""
    assert "test-key" not in result_files[0].read_text(encoding="utf-8")


def test_lane_bakeoff_prompt_does_not_leak_expected_hints() -> None:
    fixture = load_fixture(FIXTURE_DIR / "architecture_byom_lane_runtime.json")
    prompt = lane_bakeoff.build_prompt(fixture)

    assert "must_include" not in prompt
    assert "must_avoid" not in prompt
    assert "scoring" not in prompt.lower()
    assert fixture["task"] in prompt
    assert fixture["context"] in prompt


def test_lane_bakeoff_chat_completions_url_accepts_base_or_full_url() -> None:
    assert (
        lane_bakeoff.chat_completions_url("https://api.z.ai/api/coding/paas/v4")
        == "https://api.z.ai/api/coding/paas/v4/chat/completions"
    )
    assert (
        lane_bakeoff.chat_completions_url("https://example.test/v1/chat/completions")
        == "https://example.test/v1/chat/completions"
    )
