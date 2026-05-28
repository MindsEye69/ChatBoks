from __future__ import annotations

from pathlib import Path


class Summarizer:
    """Small deterministic fallback summarizer.

    The design allows this to become a fast model call later. For the scaffold,
    preserve user inputs, system events, and control signals.
    """

    def summarize(self, chatboks_md: Path) -> str:
        if not chatboks_md.exists():
            return "[SUMMARY] No prior chatboks log."
        full = chatboks_md.read_text(encoding="utf-8")
        key_lines = []
        for line in full.splitlines():
            stripped = line.strip()
            if (
                stripped.startswith("[YOU]")
                or stripped.startswith("[SYSTEM]")
                or stripped.startswith(">>>")
            ):
                key_lines.append(stripped)
        if not key_lines:
            return "[SUMMARY] No decision lines found."
        return "[SUMMARY]\n" + "\n".join(key_lines[-200:])
