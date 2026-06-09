from __future__ import annotations

import re
from typing import Sequence


TRANSCRIPT_TURN_RE = re.compile(
    r"^\[(YOU|CLAUDE|CODEX|AGENT_ZERO|ANTIGRAVITY|SYSTEM)\]",
    re.I,
)
SUMMARY_CHECKPOINT_START_RE = re.compile(
    r"^(?:\[(YOU|CLAUDE|CODEX|AGENT_ZERO|ANTIGRAVITY|SYSTEM)\]\s+)?>>> SUMMARY_CHECKPOINT\b",
    re.I,
)
SUMMARY_CHECKPOINT_END_RE = re.compile(r"^>>> SUMMARY_CHECKPOINT_END\b", re.I)


def is_transcript_turn(line: str) -> bool:
    return bool(TRANSCRIPT_TURN_RE.match(line.strip()))


def is_summary_checkpoint_start(line: str) -> bool:
    return bool(SUMMARY_CHECKPOINT_START_RE.match(line.strip()))


def is_summary_checkpoint_end(line: str) -> bool:
    return bool(SUMMARY_CHECKPOINT_END_RE.match(line.strip()))


def find_last_summary_checkpoint(lines: Sequence[str]) -> tuple[int, int] | None:
    for index in range(len(lines) - 1, -1, -1):
        if is_summary_checkpoint_start(lines[index]):
            return index, find_summary_checkpoint_end(lines, index)
    return None


def find_summary_checkpoint_end(lines: Sequence[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        if is_summary_checkpoint_end(lines[index]):
            return index + 1
    return len(lines)


def extract_summary_items(lines: Sequence[str], start: int, end: int) -> list[str]:
    items: list[str] = []
    in_summary = False
    for line in lines[start:end]:
        stripped = line.strip()
        if not stripped:
            continue
        if is_summary_checkpoint_end(stripped):
            break
        if stripped == "[SUMMARY]":
            in_summary = True
            continue
        if not in_summary:
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        items.append(stripped)
    return items
