from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.claude import ClaudeAgent
from agents.codex import CodexAgent, CodexSparkAgent
from doctor import adapter_profile_known


def test_codex_adapter_profile_expands_project_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agent = CodexAgent(
            root,
            {"cli": "codex", "adapter_profile": "codex_exec_v1"},
            "role",
        )

        command = agent.command()

        assert command == [
            "codex",
            "exec",
            "-C",
            str(root),
            "--dangerously-bypass-approvals-and-sandbox",
            "-s",
            "danger-full-access",
            "-",
        ]


def test_codex_spark_adapter_profile_uses_spark_model():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agent = CodexSparkAgent(
            root,
            {"cli": "codex", "adapter_profile": "codex_spark_exec_v1"},
            "role",
        )

        command = agent.command()

        assert command == [
            "codex",
            "exec",
            "-C",
            str(root),
            "-m",
            "gpt-5.3-codex-spark",
            "--dangerously-bypass-approvals-and-sandbox",
            "-s",
            "danger-full-access",
            "-",
        ]


def test_adapter_args_override_named_profile():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agent = ClaudeAgent(
            root,
            {
                "cli": "claude",
                "adapter_profile": "unknown_future_profile",
                "adapter_args": ["--print", "--cwd", "{project_path}"],
            },
            "role",
        )

        assert agent.command() == ["claude", "--print", "--cwd", str(root)]


def test_doctor_accepts_known_profile_and_rejects_unknown_profile():
    assert adapter_profile_known("codex", {"adapter_profile": "codex_exec_v1"})
    assert adapter_profile_known("codex_spark", {"adapter_profile": "codex_spark_exec_v1"})
    assert not adapter_profile_known("codex", {"adapter_profile": "codex_exec_v9"})
    assert not adapter_profile_known("codex_spark", {"adapter_profile": "codex_spark_exec_v9"})
    assert adapter_profile_known(
        "codex",
        {
            "adapter_profile": "codex_exec_v1",
            "fallback_profiles": ["codex_exec_v1"],
        },
    )
    assert not adapter_profile_known(
        "codex",
        {
            "adapter_profile": "codex_exec_v1",
            "fallback_profiles": ["codex_exec_v9"],
        },
    )
    assert adapter_profile_known(
        "codex",
        {"adapter_profile": "codex_exec_v9", "adapter_args": ["exec", "-"]},
    )


if __name__ == "__main__":
    test_codex_adapter_profile_expands_project_path()
    test_codex_spark_adapter_profile_uses_spark_model()
    test_adapter_args_override_named_profile()
    test_doctor_accepts_known_profile_and_rejects_unknown_profile()
    print("All adapter profile smoke tests passed.")
