from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.base import AgentTimeoutError, BaseAgent, TokenExhaustionError


class ScriptAgent(BaseAgent):
    name = "script"

    def __init__(self, script_path: Path, project_path: Path) -> None:
        super().__init__(
            project_path=project_path,
            config={"cli": sys.executable},
            role="test role",
        )
        self.script_path = script_path

    def command(self, adapter_override: dict[str, object] | None = None) -> list[str]:
        return [self.cli, str(self.script_path)]


class FallbackAgent(BaseAgent):
    name = "fallback"
    default_adapter_profile = "primary"
    adapter_profiles = {
        "primary": ["--model", "pro"],
        "fallback": ["--model", "flash"],
    }
    default_args = adapter_profiles["primary"]

    def __init__(self, root: Path) -> None:
        super().__init__(
            project_path=root,
            config={
                "cli": "fallback-cli",
                "adapter_profile": "primary",
                "fallback_profiles": ["fallback"],
            },
            role="test role",
        )
        self.commands_seen: list[list[str]] = []

    def run_cli_once(
        self,
        prompt: str,
        command: list[str],
        timeout: float = 120,
        idle_timeout: float | None = None,
        max_timeout: float | None = None,
    ) -> str:
        self.commands_seen.append(command)
        if "pro" in command:
            raise TokenExhaustionError("prompt is too long for pro")
        return f"used {' '.join(command)}\n>>> TASK_COMPLETE"


def run_script(script: str, prompt: str = "hello", **kwargs: float) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script_path = root / "child.py"
        script_path.write_text(script, encoding="utf-8")
        return ScriptAgent(script_path, root).run_cli(prompt, **kwargs)


def test_streaming_run_cli_returns_successful_stdout() -> None:
    script = (
        "import sys\n"
        "prompt = sys.stdin.read().strip()\n"
        "print('first line')\n"
        "print(prompt)\n"
        "print('>>> TASK_COMPLETE')\n"
    )

    result = run_script(script, prompt="hello from stdin", timeout=5)

    assert result == "first line\nhello from stdin\n>>> TASK_COMPLETE"


def test_streaming_run_cli_forces_utf8_child_environment() -> None:
    script = (
        "import os, sys\n"
        "sys.stdin.read()\n"
        "print(os.environ.get('PYTHONUTF8'))\n"
        "print(os.environ.get('PYTHONIOENCODING'))\n"
        "print('>>> TASK_COMPLETE')\n"
    )

    result = run_script(script, timeout=5)

    assert result == "1\nutf-8\n>>> TASK_COMPLETE"


def test_streaming_run_cli_idle_timeout_resets_on_output() -> None:
    script = (
        "import sys, time\n"
        "sys.stdin.read()\n"
        "print('started', flush=True)\n"
        "time.sleep(1)\n"
        "print('finished', flush=True)\n"
    )

    with pytest.raises(AgentTimeoutError) as exc_info:
        run_script(script, idle_timeout=0.2, max_timeout=5)

    error = exc_info.value
    assert error.reason == "idle"
    assert error.timeout_seconds == 0.2
    assert error.partial_output == "started"


def test_streaming_run_cli_enforces_absolute_max_timeout() -> None:
    script = (
        "import sys, time\n"
        "sys.stdin.read()\n"
        "end = time.monotonic() + 2\n"
        "while time.monotonic() < end:\n"
        "    print('tick', flush=True)\n"
        "    time.sleep(0.05)\n"
    )

    with pytest.raises(AgentTimeoutError) as exc_info:
        run_script(script, idle_timeout=1, max_timeout=0.25)

    error = exc_info.value
    assert error.reason == "max"
    assert error.timeout_seconds == 0.25
    assert "tick" in error.partial_output


def test_dynamic_idle_timeout_scales_with_prompt_size() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script_path = root / "child.py"
        script_path.write_text("import sys\nsys.stdin.read()\nprint('ok')\n", encoding="utf-8")
        agent = ScriptAgent(script_path, root)
        agent.config["timeout_prompt_chars_per_step"] = 10
        agent.config["timeout_seconds_per_step"] = 2

        idle_timeout, max_timeout = agent.resolve_timeouts("x" * 25, 5, None, 20)

        assert idle_timeout == 9
        assert max_timeout == 20


def test_streaming_run_cli_reports_nonzero_stderr() -> None:
    script = (
        "import sys\n"
        "sys.stdin.read()\n"
        "print('bad stderr', file=sys.stderr)\n"
        "raise SystemExit(7)\n"
    )

    result = run_script(script, timeout=5)

    assert result == "CLI call failed for script: bad stderr\n>>> BLOCKED"


def test_streaming_run_cli_detects_token_exhaustion_on_failure() -> None:
    script = (
        "import sys\n"
        "sys.stdin.read()\n"
        "print('context length exceeded', file=sys.stderr)\n"
        "raise SystemExit(1)\n"
    )

    with pytest.raises(TokenExhaustionError, match="context length exceeded"):
        run_script(script, timeout=5)


def test_call_uses_extended_max_timeout_for_streaming_heartbeat() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script_path = root / "child.py"
        script_path.write_text(
            "import sys\n"
            "sys.stdin.read()\n"
            "print('ok')\n"
            "print('>>> TASK_COMPLETE')\n",
            encoding="utf-8",
        )
        agent = ScriptAgent(script_path, root)

        result = agent.call("context")

        assert result == "ok\n>>> TASK_COMPLETE"


def test_run_cli_falls_back_to_secondary_adapter_profile_after_token_exhaustion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        agent = FallbackAgent(Path(tmp))

        result = agent.run_cli("context", timeout=5)

        assert result == "used fallback-cli --model flash\n>>> TASK_COMPLETE"
        assert agent.commands_seen == [
            ["fallback-cli", "--model", "pro"],
            ["fallback-cli", "--model", "flash"],
        ]
        assert agent.last_adapter_profile_used == "fallback"
        assert agent.last_adapter_fallback_used is True


if __name__ == "__main__":
    tests = [
        test_streaming_run_cli_returns_successful_stdout,
        test_streaming_run_cli_idle_timeout_resets_on_output,
        test_streaming_run_cli_enforces_absolute_max_timeout,
        test_dynamic_idle_timeout_scales_with_prompt_size,
        test_streaming_run_cli_reports_nonzero_stderr,
        test_streaming_run_cli_detects_token_exhaustion_on_failure,
        test_call_uses_extended_max_timeout_for_streaming_heartbeat,
        test_run_cli_falls_back_to_secondary_adapter_profile_after_token_exhaustion,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
