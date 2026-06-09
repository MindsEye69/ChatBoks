from __future__ import annotations

from pathlib import Path

from context.transcript import (
    extract_summary_items,
    find_last_summary_checkpoint,
    is_summary_checkpoint_end,
    is_summary_checkpoint_start,
)


class Summarizer:
    """Small deterministic fallback summarizer.

    The design allows this to become a fast model call later. For the scaffold,
    preserve user inputs, system events, and control signals.
    """

    def __init__(self, max_items: int = 32) -> None:
        self.max_items = max(1, int(max_items))

    def summarize(self, chatboks_md: Path) -> str:
        if not chatboks_md.exists():
            return "[SUMMARY] No prior chatboks log."
        lines = chatboks_md.read_text(encoding="utf-8").splitlines()
        key_lines = self.summary_seed(lines)
        if not key_lines:
            return "[SUMMARY] No decision lines found."
        return "[SUMMARY]\n" + "\n".join(f"- {line}" for line in key_lines[-self.max_items :])

    def summary_seed(self, lines: list[str]) -> list[str]:
        checkpoint = find_last_summary_checkpoint(lines)
        preserved: list[str] = []
        fresh_lines = lines
        if checkpoint is not None:
            start, end = checkpoint
            preserved = extract_summary_items(lines, start, end)
            fresh_lines = lines[end:]

        items = [*preserved, *self.collect_key_lines(fresh_lines)]
        normalized: list[str] = []
        for item in items:
            collapsed = " ".join(item.split())
            if not collapsed:
                continue
            if normalized and normalized[-1] == collapsed:
                continue
            normalized.append(collapsed)
        return normalized

    @staticmethod
    def collect_key_lines(lines: list[str]) -> list[str]:
        key_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if is_summary_checkpoint_start(stripped) or is_summary_checkpoint_end(stripped):
                continue
            if stripped.startswith("[YOU]") or stripped.startswith("[SYSTEM]") or ">>>" in stripped:
                key_lines.append(stripped)
        return key_lines
