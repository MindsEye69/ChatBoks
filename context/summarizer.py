from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from context.packets import packet_records_from_jsonl
from context.transcript import (
    extract_summary_items,
    find_last_summary_checkpoint,
    is_summary_checkpoint_end,
    is_summary_checkpoint_start,
)


TURN_RE = re.compile(r"^\[(YOU|CLAUDE|CODEX|CODEX_SPARK|AGENT_ZERO|ANTIGRAVITY|ANTIGRAV|SYSTEM)\]\s*(.*)$", re.I)
CONTROL_RE = re.compile(r"^>>>\s+(TASK_COMPLETE|HANDOFF|QUESTION|BLOCKED|PROPOSAL)\b", re.I)


class Summarizer:
    """Small deterministic fallback summarizer.

    The design allows this to become a fast model call later. For now, preserve
    durable project memory while filtering routine control chatter.
    """

    SECTION_ORDER = [
        "Decisions",
        "Open risks",
        "Pending tasks",
        "Verified facts",
        "Tests and commits",
        "Unresolved handoffs/questions",
        "Recent user requests",
        "Prior memory",
    ]

    def __init__(self, max_items: int = 32) -> None:
        self.max_items = max(1, int(max_items))

    def summarize(self, chatboks_md: Path) -> str:
        if not chatboks_md.exists():
            return "[SUMMARY] No prior chatboks log."
        lines = chatboks_md.read_text(encoding="utf-8-sig").splitlines()
        sections = self.summary_sections(lines, packet_path=self.packet_path_for(chatboks_md))
        if not any(sections.values()):
            return "[SUMMARY] No decision lines found."

        remaining = self.max_items
        out = ["[SUMMARY]"]
        for section in self.SECTION_ORDER:
            items = sections.get(section, [])
            if not items or remaining <= 0:
                continue
            selected = items[-remaining:]
            out.append(f"{section}:")
            out.extend(f"- {item}" for item in selected)
            remaining -= len(selected)
        return "\n".join(out)

    def summary_sections(self, lines: list[str], packet_path: Path | None = None) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {section: [] for section in self.SECTION_ORDER}
        self.add_packet_sections(sections, packet_path)
        checkpoint = find_last_summary_checkpoint(lines)
        fresh_lines = lines
        if checkpoint is not None:
            start, end = checkpoint
            for item in extract_summary_items(lines, start, end):
                normalized = self.normalize_item(item)
                if normalized and not normalized.endswith(":") and not self.is_low_signal_prior(normalized):
                    self.add_item(sections, "Prior memory", normalized)
            fresh_lines = lines[end:]

        for sender, body in self.parse_turns(fresh_lines):
            self.classify_turn(sections, sender, body)
        return sections

    def add_packet_sections(self, sections: dict[str, list[str]], packet_path: Path | None) -> None:
        if packet_path is None or not packet_path.exists():
            return
        text = packet_path.read_text(encoding="utf-8-sig", errors="replace")
        for record in packet_records_from_jsonl(text, limit=self.max_items * 2):
            packet = record.get("packet")
            if not isinstance(packet, dict):
                continue
            self.classify_packet(sections, packet)

    def classify_packet(self, sections: dict[str, list[str]], packet: dict[str, Any]) -> None:
        agent = self.normalize_item(packet.get("agent") or "agent")
        stance = self.normalize_item(packet.get("stance") or "").upper()
        signal = self.normalize_item(packet.get("signal") or "").upper()
        for item in packet.get("observed") or []:
            self.add_item(sections, "Verified facts", f"{agent} {stance}: {item}")
        for item in packet.get("risks") or []:
            self.add_item(sections, "Open risks", f"{agent} {stance}: {item}")
        next_action = self.normalize_item(packet.get("next_action") or "")
        if next_action and next_action.lower() not in {"none", "n/a", "na"}:
            self.add_item(sections, "Pending tasks", f"{agent}: {next_action}")
        if signal in {"HANDOFF", "QUESTION", "BLOCKED", "PROPOSAL"}:
            self.add_item(sections, "Unresolved handoffs/questions", f"{agent} {signal}: {next_action or stance}")

    def classify_turn(self, sections: dict[str, list[str]], sender: str, body: str) -> None:
        cleaned = self.clean_body(body)
        if not cleaned or self.is_routine(cleaned):
            return

        lower = cleaned.lower()
        if sender == "SYSTEM":
            if "commit by" in lower:
                self.add_item(sections, "Tests and commits", cleaned)
            elif "collaboration mode set" in lower or "context mode set" in lower:
                self.add_item(sections, "Decisions", cleaned)
            elif "blocked" in lower or "question raised" in lower or "handoff" in lower:
                self.add_item(sections, "Unresolved handoffs/questions", cleaned)
            return

        if sender == "YOU":
            self.add_item(sections, "Recent user requests", cleaned)
            return

        if any(marker in lower for marker in ("blocked", "question", "handoff", "proposal")):
            self.add_item(sections, "Unresolved handoffs/questions", cleaned)
        if any(marker in lower for marker in ("risk", "challenge", "missing", "failure", "failed", "blocker")):
            self.add_item(sections, "Open risks", cleaned)
        if any(marker in lower for marker in ("verified", "observed", "implemented", "fixed", "added", "changed")):
            self.add_item(sections, "Verified facts", cleaned)
        if any(marker in lower for marker in ("test", "pytest", "passed", "commit", "build")):
            self.add_item(sections, "Tests and commits", cleaned)
        if lower.startswith(("decision:", "decided", "agreed")):
            self.add_item(sections, "Decisions", cleaned)

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

    @staticmethod
    def packet_path_for(chatboks_md: Path) -> Path:
        return chatboks_md.parent / ".chatboks" / "packets.jsonl"

    @staticmethod
    def parse_turns(lines: list[str]) -> list[tuple[str, str]]:
        turns: list[tuple[str, list[str]]] = []
        current_sender: str | None = None
        current_body: list[str] = []
        for line in lines:
            stripped = line.strip()
            if is_summary_checkpoint_start(stripped) or is_summary_checkpoint_end(stripped):
                continue
            match = TURN_RE.match(line)
            if match:
                if current_sender is not None:
                    turns.append((current_sender, current_body))
                current_sender = match.group(1).upper()
                current_body = [match.group(2).strip()]
            elif current_sender is not None:
                current_body.append(line.strip())
        if current_sender is not None:
            turns.append((current_sender, current_body))
        return [(sender, "\n".join(body)) for sender, body in turns]

    @classmethod
    def clean_body(cls, body: str) -> str:
        lines: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if CONTROL_RE.match(stripped) and "TASK_COMPLETE" in stripped.upper():
                continue
            if stripped.lower().startswith("session tokens:"):
                continue
            if stripped.startswith("Verifier instructions:"):
                break
            lines.append(stripped)
        return cls.normalize_item(" ".join(lines))

    @staticmethod
    def normalize_item(item: str) -> str:
        stripped = item.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        return " ".join(stripped.split())[:600]

    @staticmethod
    def is_routine(text: str) -> bool:
        lower = text.lower().strip()
        if CONTROL_RE.match(text):
            return True
        if lower in {"role call", "roll call"}:
            return True
        if lower.endswith(" role call") or lower.endswith(" roll call"):
            return True
        if "online" in lower and "role" in lower and len(lower) < 240:
            return True
        if lower.startswith("remote bridge ready"):
            return True
        if lower.startswith("command accepted. waiting for agents"):
            return True
        if lower.startswith("sleep complete."):
            return True
        return False

    @classmethod
    def is_low_signal_prior(cls, text: str) -> bool:
        lower = text.lower().strip()
        if lower.startswith(">>> proposal"):
            return False
        if cls.is_routine(text):
            return True
        if lower.startswith("[system] confirmation mode"):
            return True
        if "reply >>>" in lower:
            return True
        if lower.startswith("[you] role call") or lower.startswith("[you] roll call"):
            return True
        if lower.startswith("[you]") and ("what's next" in lower or "what project space" in lower):
            return True
        if lower.startswith("[you]") and "no-edit" in lower and "smoke" in lower:
            return True
        return False

    @classmethod
    def add_item(cls, sections: dict[str, list[str]], section: str, item: str) -> None:
        normalized = cls.normalize_item(item)
        if not normalized:
            return
        bucket = sections.setdefault(section, [])
        if normalized not in bucket:
            bucket.append(normalized)
