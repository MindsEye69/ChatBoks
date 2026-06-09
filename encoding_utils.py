from __future__ import annotations

import os
import sys


def configure_utf8_stdio() -> None:
    """Prefer UTF-8 for ChatBoks console/process I/O on every platform."""
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        kwargs = {"encoding": "utf-8"}
        if stream_name in {"stdout", "stderr"}:
            kwargs["errors"] = "replace"
        try:
            reconfigure(**kwargs)
        except (OSError, ValueError):
            pass


def utf8_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment that makes Python children speak UTF-8."""
    result = dict(os.environ if env is None else env)
    result["PYTHONUTF8"] = "1"
    result["PYTHONIOENCODING"] = "utf-8"
    return result
