"""Tests for F3: trusted role-file approval (trust.py).

Covers:
- First approval: interactive, user approves -> content returned, hash stored
- Hash match: existing approval, content unchanged -> content returned, no prompt
- Hash mismatch fallback: non-interactive -> None returned
- Rejection fallback: user rejects -> None returned, hash not stored
- Symlink escape: symlink target outside project directory -> None returned
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import trust as trust_mod
from router import Router
from trust import (
    load_role_with_approval,
    _approval_path,
    _load_approved_hash,
    _prompt_approval,
    _save_approved_hash,
    _safe_preview_line,
    _sha256,
    _resolve_safe,
)


def _approval_dir(tmp: str) -> Path:
    return Path(tmp) / ".test-approvals"


# ---------------------------------------------------------------------------
# First approval
# ---------------------------------------------------------------------------

def test_first_approval_interactive_user_approves_returns_content():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        content = "You are Claude in ChatBoks.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            with patch("builtins.input", return_value="y"):
                result = load_role_with_approval(project, role_file, interactive=True)

        assert result == content


def test_first_approval_interactive_hash_stored_after_approval():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        content = "You are Claude in ChatBoks.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            with patch("builtins.input", return_value="y"):
                load_role_with_approval(project, role_file, interactive=True)
            stored = _load_approved_hash(project, role_file)

        assert stored == _sha256(content)


def test_approval_pin_is_stored_outside_project():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        approval_dir = Path(tmp) / "approvals"

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            pin_path = _approval_path(project, "CLAUDE.md")

        assert approval_dir in pin_path.parents
        assert project not in pin_path.parents


# ---------------------------------------------------------------------------
# Hash match (no prompt)
# ---------------------------------------------------------------------------

def test_hash_match_returns_content_without_prompting():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "AGENTS.md"
        content = "You are Codex in ChatBoks.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            _save_approved_hash(project, role_file, _sha256(content))
            with patch("builtins.input") as mock_input:
                result = load_role_with_approval(project, role_file, interactive=True)
            mock_input.assert_not_called()

        assert result == content


def test_hash_match_non_interactive_returns_content():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "AGENTS.md"
        content = "You are Codex.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            _save_approved_hash(project, role_file, _sha256(content))
            result = load_role_with_approval(project, role_file, interactive=False)

        assert result == content


# ---------------------------------------------------------------------------
# Hash mismatch fallback
# ---------------------------------------------------------------------------

def test_hash_mismatch_non_interactive_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        old_content = "Old role content.\n"
        new_content = "New role content - possibly injected.\n"
        (project / role_file).write_text(new_content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            _save_approved_hash(project, role_file, _sha256(old_content))
            result = load_role_with_approval(project, role_file, interactive=False)

        assert result is None


def test_hash_mismatch_interactive_user_reapproves_returns_new_content():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        old_content = "Old role content.\n"
        new_content = "New role content.\n"
        (project / role_file).write_text(new_content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            _save_approved_hash(project, role_file, _sha256(old_content))
            with patch("builtins.input", return_value="y"):
                result = load_role_with_approval(project, role_file, interactive=True)
            stored = _load_approved_hash(project, role_file)

        assert result == new_content
        assert stored == _sha256(new_content)


# ---------------------------------------------------------------------------
# Rejection fallback
# ---------------------------------------------------------------------------

def test_rejection_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        content = "You are Claude.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            with patch("builtins.input", return_value="n"):
                result = load_role_with_approval(project, role_file, interactive=True)

        assert result is None


def test_rejection_does_not_store_hash():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        content = "You are Claude.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            with patch("builtins.input", return_value="n"):
                load_role_with_approval(project, role_file, interactive=True)
            stored = _load_approved_hash(project, role_file)

        assert stored is None


def test_non_interactive_no_prior_approval_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)
        role_file = "CLAUDE.md"
        (project / role_file).write_text("Some role.\n", encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            result = load_role_with_approval(project, role_file, interactive=False)

        assert result is None


# ---------------------------------------------------------------------------
# Symlink escape
# ---------------------------------------------------------------------------

def test_symlink_escape_outside_project_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        outside = Path(tmp) / "evil.md"
        outside.write_text("malicious instructions\n", encoding="utf-8")
        symlink = project / "CLAUDE.md"
        try:
            symlink.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not available on this platform/permission level")

        approval_dir = Path(tmp) / ".approvals"
        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            result = load_role_with_approval(project, "CLAUDE.md", interactive=False)

        assert result is None


def test_safe_file_within_project_is_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        approval_dir = Path(tmp) / ".approvals"
        role_file = "CLAUDE.md"
        content = "You are Claude.\n"
        (project / role_file).write_text(content, encoding="utf-8")

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            _save_approved_hash(project, role_file, _sha256(content))
            result = load_role_with_approval(project, role_file, interactive=False)

        assert result == content


def test_missing_role_file_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        approval_dir = _approval_dir(tmp)

        with patch.object(trust_mod, "_APPROVED_DIR", approval_dir):
            result = load_role_with_approval(project, "NONEXISTENT.md", interactive=False)

        assert result is None


def test_resolve_safe_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        outside = Path(tmp) / "outside.md"
        outside.write_text("evil\n", encoding="utf-8")
        # Directory traversal via role_filename
        result = _resolve_safe(project, "../outside.md")
        assert result is None


def test_resolve_safe_accepts_normal_file():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "CLAUDE.md").write_text("ok\n", encoding="utf-8")
        result = _resolve_safe(project, "CLAUDE.md")
        assert result is not None
        assert result.name == "CLAUDE.md"


# ---------------------------------------------------------------------------
# Terminal-safe preview
# ---------------------------------------------------------------------------

def test_safe_preview_line_escapes_control_characters():
    assert _safe_preview_line("ok\t\x1b[31mred\x7f") == r"ok\t\x1b[31mred\x7f"


def test_prompt_approval_preview_does_not_emit_raw_escape_sequences(capsys):
    resolved = Path("C:/tmp/CLAUDE.md")
    with patch("builtins.input", return_value="n"):
        _prompt_approval(resolved, "CLAUDE.md", "\x1b[31mred\x1b[0m\n", "first use")

    out = capsys.readouterr().out
    assert "\\x1b[31mred\\x1b[0m" in out
    assert "\x1b[31mred\x1b[0m" not in out


# ---------------------------------------------------------------------------
# Router fallback
# ---------------------------------------------------------------------------

def test_router_unapproved_project_role_falls_back_to_installed_role():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "COORDINATOR.md").write_text(
            "Project-local role must not load.\n",
            encoding="utf-8",
        )
        router = Router(
            {
                "projects": {"chatboks": {"agents": ["coordinator"]}},
                "agents": {"coordinator": {}},
            },
            "chatboks",
            project,
        )

        with patch("router.load_role_with_approval", return_value=None):
            result = router.load_role("coordinator", {"role_file": "COORDINATOR.md"})

        assert "Project-local role must not load" not in result
        assert "ChatBoks Collaboration Protocol" in result
        assert "Coordinator's Role - ChatBoks" in result


def test_router_fallback_uses_role_basename_only():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        router = Router(
            {
                "projects": {"chatboks": {"agents": ["coordinator"]}},
                "agents": {"coordinator": {}},
            },
            "chatboks",
            project,
        )

        with patch("router.load_role_with_approval", return_value=None):
            result = router.load_role("coordinator", {"role_file": "../COORDINATOR.md"})

        assert "ChatBoks Collaboration Protocol" in result
        assert "Coordinator's Role - ChatBoks" in result


def test_router_prepends_protocol_to_approved_project_role():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        router = Router(
            {
                "projects": {"chatboks": {"agents": ["coordinator"]}},
                "agents": {"coordinator": {}},
            },
            "chatboks",
            project,
        )

        with patch("router.load_role_with_approval", return_value="Project approved role.\n"):
            result = router.load_role("coordinator", {"role_file": "COORDINATOR.md"})

        assert result.startswith("# ChatBoks Collaboration Protocol")
        assert "Project approved role." in result


def test_router_prepends_protocol_to_default_role():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        router = Router(
            {
                "projects": {"chatboks": {"agents": ["missing_agent"]}},
                "agents": {"missing_agent": {}},
            },
            "chatboks",
            project,
        )

        result = router.load_role("missing_agent", {})

        assert result.startswith("# ChatBoks Collaboration Protocol")
        assert "You are missing_agent in Chatboks" in result


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
