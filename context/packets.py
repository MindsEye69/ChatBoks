from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


PACKET_START_RE = re.compile(r"^\s*>>>\s+PACKET\s*$", re.I)
PACKET_END_RE = re.compile(r"^\s*>>>\s+PACKET_END\s*$", re.I)
VALID_STANCES = {"ADD", "VERIFY", "CHALLENGE", "SKIP", "HANDOFF"}
VALID_SIGNALS = {"TASK_COMPLETE", "HANDOFF", "BLOCKED", "QUESTION", "PROPOSAL", "SKIP"}


@dataclass(frozen=True)
class ThoughtPacket:
    agent: str
    stance: str
    observed: list[str]
    risks: list[str]
    next_action: str
    signal: str

    def to_record(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "stance": self.stance,
            "observed": self.observed,
            "risks": self.risks,
            "next_action": self.next_action,
            "signal": self.signal,
        }


def extract_packets(text: str, fallback_agent: str = "") -> list[ThoughtPacket]:
    packets: list[ThoughtPacket] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not PACKET_START_RE.match(lines[index]):
            index += 1
            continue
        start = index + 1
        index = start
        body: list[str] = []
        while index < len(lines) and not PACKET_END_RE.match(lines[index]):
            body.append(lines[index])
            index += 1
        if index < len(lines) and PACKET_END_RE.match(lines[index]):
            packet = parse_packet_body(body, fallback_agent=fallback_agent)
            if packet is not None:
                packets.append(packet)
        index += 1
    return packets


def parse_packet_body(lines: list[str], fallback_agent: str = "") -> ThoughtPacket | None:
    data: dict[str, Any] = {
        "observed": [],
        "risks": [],
    }
    current_list: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if current_list and stripped.startswith("- "):
            value = normalize_value(stripped[2:])
            if value:
                data[current_list].append(value)
            continue
        current_list = None
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip().lower().replace("-", "_")
        value = normalize_value(raw_value)
        if key in {"observed", "risks"}:
            current_list = key
            if value:
                data[key].append(value)
            continue
        if key in {"agent", "stance", "next_action", "signal"}:
            data[key] = value

    agent = normalize_value(data.get("agent") or fallback_agent).lower()
    stance = normalize_value(data.get("stance")).upper()
    signal = normalize_value(data.get("signal")).upper().replace(" ", "_")
    next_action = normalize_value(data.get("next_action"))
    observed = clean_list(data.get("observed"))
    risks = clean_list(data.get("risks"))
    if not agent or stance not in VALID_STANCES or signal not in VALID_SIGNALS:
        return None
    return ThoughtPacket(
        agent=agent,
        stance=stance,
        observed=observed,
        risks=risks,
        next_action=next_action,
        signal=signal,
    )


def normalize_value(value: Any) -> str:
    return " ".join(str(value or "").strip().split())[:600]


def clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        normalized = normalize_value(value)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def packet_records_from_jsonl(text: str, limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and isinstance(item.get("packet"), dict):
            records.append(item)
    return records[-limit:] if limit is not None else records
