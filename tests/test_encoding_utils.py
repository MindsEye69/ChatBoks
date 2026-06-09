from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from encoding_utils import utf8_env


def test_utf8_env_overrides_hostile_python_encoding() -> None:
    env = utf8_env({"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252", "KEEP": "yes"})

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["KEEP"] == "yes"


def test_stream_reconfigures_stdio_before_rich_output() -> None:
    repo = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "cp1252"
    script = (
        "from ui.stream import Stream\n"
        "Stream({}, []).system('UTF-8 smoke: box drawing ─ and check mark ✓')\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "UnicodeEncodeError" not in result.stderr
