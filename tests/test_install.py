from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import install


def test_ensure_coordinator_ollama_defaults_to_gemma3_4b():
    with patch("install.fetch_ollama_models", return_value={"gemma3:4b"}):
        assert install.ensure_coordinator_ollama({"agents": {"coordinator": {}}}, assume_yes=False)
    print("PASS: installer checks for gemma3:4b by default")
