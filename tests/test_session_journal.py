"""Tests for durable session journal writes."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from session_journal import atomic_write_text


def test_atomic_write_retries_transient_windows_replace_lock(tmp_path: Path) -> None:
    destination = tmp_path / "snapshot.json"
    real_replace = os.replace
    attempts = 0

    def temporarily_locked(source: Path, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("temporarily locked")
        real_replace(source, target)

    with patch("session_journal.os.replace", side_effect=temporarily_locked):
        atomic_write_text(destination, '{"status": "idle"}')

    assert attempts == 3
    assert destination.read_text(encoding="utf-8") == '{"status": "idle"}'
    assert not list(tmp_path.glob(".*.tmp"))
