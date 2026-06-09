"""F3: Trusted role-file approval.

Role files (CLAUDE.md, AGENTS.md, etc.) live in the project directory and are
passed verbatim to agents as system context.  A malicious or tampered role file
is a prompt-injection vector.  This module guards that load path:

1. Resolve symlinks and reject any file whose real path is outside the project.
2. SHA-256 the file content and compare against an out-of-project approval store
   at ~/.chatboks/approved-roles/<project-hash>/<role-basename>.sha256.
3. In interactive mode (stdin is a TTY), prompt the user on first use or hash
   mismatch.  Approved -> store hash and return content.  Rejected -> None.
4. In non-interactive mode (CI, headless), return None on any approval failure.
   Caller falls back to the installed role file or the hard-coded default role.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


_RUNTIME_HOME = Path("~/.chatboks").expanduser()
_APPROVED_DIR = _RUNTIME_HOME / "approved-roles"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _project_hash(project_path: Path) -> str:
    canonical = str(project_path.resolve())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _approval_path(project_path: Path, role_filename: str) -> Path:
    safe_name = Path(role_filename).name  # strip any injected directory component
    return _APPROVED_DIR / _project_hash(project_path) / f"{safe_name}.sha256"


def _load_approved_hash(project_path: Path, role_filename: str) -> str | None:
    path = _approval_path(project_path, role_filename)
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None


def _save_approved_hash(project_path: Path, role_filename: str, digest: str) -> None:
    path = _approval_path(project_path, role_filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest + "\n", encoding="utf-8")


def _resolve_safe(project_path: Path, role_filename: str) -> Path | None:
    """Return the resolved path only if it stays within the project directory.

    Resolves symlinks so a symlink pointing outside the project is caught.
    Returns None if the resolved path escapes the project root.
    """
    candidate = (project_path / role_filename).resolve()
    project_root = project_path.resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError:
        return None
    return candidate


def _prompt_approval(resolved: Path, role_filename: str, content: str, reason: str) -> bool:
    """Show the role file preview and ask the user to approve."""
    digest = _sha256(content)
    print(f"\n[ChatBoks] Role file trust check: {role_filename} ({reason})")
    print(f"  Resolved path : {resolved}")
    print(f"  SHA-256       : {digest}")
    print("  Preview (first 5 lines):")
    for line in content.splitlines()[:5]:
        print(f"    {_safe_preview_line(line)}")
    print()
    try:
        answer = input("  Approve loading this role file? [y/N] ").strip().lower()
    except (EOFError, OSError):
        answer = "n"
    return answer in {"y", "yes"}


def _safe_preview_line(text: str) -> str:
    preview: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char == "\t":
            preview.append("\\t")
        elif char == "\r":
            preview.append("\\r")
        elif char == "\n":
            preview.append("\\n")
        elif codepoint < 32 or codepoint == 127:
            preview.append(f"\\x{codepoint:02x}")
        else:
            preview.append(char)
    return "".join(preview)


def load_role_with_approval(
    project_path: Path,
    role_filename: str,
    *,
    interactive: bool | None = None,
) -> str | None:
    """Load a project-local role file only if approved.

    Returns the file content string when approved, or None when the file should
    not be loaded (unapproved, rejected, symlink escape, or file missing).
    The caller should fall back to an installed role file or the default role.

    Parameters
    ----------
    project_path:
        Absolute path to the project root.
    role_filename:
        Relative name of the role file (e.g. ``CLAUDE.md``).
    interactive:
        Override TTY detection for tests.  When None (default) the function
        calls ``sys.stdin.isatty()``.
    """
    if interactive is None:
        interactive = sys.stdin.isatty()

    resolved = _resolve_safe(project_path, role_filename)
    if resolved is None or not resolved.exists():
        return None

    content = resolved.read_text(encoding="utf-8")
    content_hash = _sha256(content)
    approved_hash = _load_approved_hash(project_path, role_filename)

    if approved_hash == content_hash:
        return content

    if not interactive:
        return None

    reason = "first use" if approved_hash is None else "file changed since last approval"
    if _prompt_approval(resolved, role_filename, content, reason):
        _save_approved_hash(project_path, role_filename, content_hash)
        return content

    return None
