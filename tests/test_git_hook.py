from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hook_post_commit import load_state
from install import build_post_commit_hook, ensure_project_hook


def test_build_post_commit_hook_uses_absolute_runner_paths():
    hook = build_post_commit_hook(
        project="chatboks",
        python_exe=Path("C:/Python/python.exe"),
        chatboks_root=Path("C:/Users/MindsEye/.chatboks"),
        config_path=Path("C:/Users/MindsEye/.chatboks/config.yaml"),
    )

    assert "ChatBoks managed post-commit hook" in hook
    assert "hook_post_commit.py" in hook
    assert "PROJECT='chatboks'" in hook
    assert "C:/Python/python.exe" in hook


def test_ensure_project_hook_writes_managed_hook():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".git" / "hooks").mkdir(parents=True)
        config = root / "config.yaml"
        config.write_text("projects: {}\n", encoding="utf-8")

        ok = ensure_project_hook(
            "chatboks",
            {"path": str(root)},
            config,
            assume_yes=True,
        )

        hook = root / ".git" / "hooks" / "post-commit"
        assert ok
        assert hook.exists()
        assert "ChatBoks managed post-commit hook" in hook.read_text(encoding="utf-8")


def test_hook_runner_load_state_accepts_utf8_bom():
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state.json"
        state.write_text('{"status": "handoff"}', encoding="utf-8-sig")

        assert load_state(state)["status"] == "handoff"


if __name__ == "__main__":
    test_build_post_commit_hook_uses_absolute_runner_paths()
    test_ensure_project_hook_writes_managed_hook()
    test_hook_runner_load_state_accepts_utf8_bom()
    print("All git hook smoke tests passed.")
