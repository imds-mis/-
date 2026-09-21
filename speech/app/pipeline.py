from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionSpeakerMap:
    roles: dict[str, str] = field(default_factory=dict)

    def role_for(self, raw_speaker: str) -> str:
        speaker = str(raw_speaker or "").strip()
        if speaker in self.roles:
            return self.roles[speaker]
        assigned = set(self.roles.values())
        if "doctor" not in assigned:
            role = "doctor"
        elif "patient" not in assigned:
            role = "patient"
        else:
            role = "patient"
        self.roles[speaker] = role
        return role


def normalize_turns(raw_turns: list[dict[str, Any]], mapping: SessionSpeakerMap) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for item in raw_turns:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = item.get("start")
        end = item.get("end")
        turns.append({
            "speaker": mapping.role_for(str(item.get("speaker") or "unknown")),
            "text": text,
            "confidence": item.get("confidence"),
            "started_ms": int(float(start) * 1000) if start is not None else item.get("started_ms"),
            "ended_ms": int(float(end) * 1000) if end is not None else item.get("ended_ms"),
        })
    return turns
