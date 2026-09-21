from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any
from urllib.request import Request, urlopen


@dataclass
class SpeakerTurn:
    speaker: str
    text: str
    confidence: float | None = None
    started_ms: int | None = None
    ended_ms: int | None = None


@dataclass
class ClinicalSuggestion:
    field_id: str
    value: Any
    confidence: float | None
    evidence_turn_indexes: list[int]


def validate_ai_result(*, declared_fields: list[dict], turns: list[SpeakerTurn], suggestions: list[ClinicalSuggestion]) -> None:
    allowed_fields = {str(field.get("id")) for field in declared_fields if field.get("id")}
    for index, turn in enumerate(turns):
        if turn.speaker not in {"doctor", "patient"}:
            raise ValueError(f"invalid speaker at turn {index}")
        if not turn.text.strip():
            raise ValueError(f"empty transcript turn at {index}")
    for suggestion in suggestions:
        if suggestion.field_id not in allowed_fields:
            raise ValueError(f"undeclared template field: {suggestion.field_id}")
        if any(i < 0 or i >= len(turns) for i in suggestion.evidence_turn_indexes):
            raise ValueError(f"invalid evidence for field: {suggestion.field_id}")


class SpeechPipelineClient:
    def __init__(self, base_url: str, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _post(self, path: str, data: bytes, headers: dict[str, str]) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _turns(payload: dict) -> list[SpeakerTurn]:
        out: list[SpeakerTurn] = []
        for item in payload.get("turns") or []:
            out.append(SpeakerTurn(
                speaker=str(item.get("speaker") or ""),
                text=str(item.get("text") or ""),
                confidence=item.get("confidence"),
                started_ms=item.get("started_ms"),
                ended_ms=item.get("ended_ms"),
            ))
        return out

    def ingest_chunk(self, *, session_id: str, chunk_id: str, audio: bytes, mime_type: str) -> list[SpeakerTurn]:
        payload = self._post(
            "/transcribe",
            audio,
            {
                "Content-Type": mime_type,
                "Accept": "application/json",
                "X-Session-ID": session_id,
                "X-Chunk-ID": chunk_id,
            },
        )
        return self._turns(payload)

    def finalize(self, *, session_id: str) -> list[SpeakerTurn]:
        payload = self._post(
            "/finalize",
            b"",
            {
                "Accept": "application/json",
                "X-Session-ID": session_id,
            },
        )
        return self._turns(payload)


class ClinicalExtractionClient:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def extract(self, *, fields: list[dict], turns: list[SpeakerTurn], system_values: dict[str, Any]) -> list[ClinicalSuggestion]:
        prompt = {
            "instruction": (
                "Extract only facts explicitly supported by the transcript into declared template fields. "
                "Never invent diagnoses, treatment or absent facts. Return JSON with key suggestions. "
                "Each suggestion must contain field_id, value, confidence and evidence_turn_indexes."
            ),
            "fields": fields,
            "turns": [asdict(turn) for turn in turns],
            "system_values": system_values,
        }
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a clinical documentation extraction engine."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        }, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        out: list[ClinicalSuggestion] = []
        for item in parsed.get("suggestions") or []:
            out.append(ClinicalSuggestion(
                field_id=str(item.get("field_id") or ""),
                value=item.get("value"),
                confidence=item.get("confidence"),
                evidence_turn_indexes=[int(i) for i in (item.get("evidence_turn_indexes") or [])],
            ))
        validate_ai_result(declared_fields=fields, turns=turns, suggestions=out)
        return out
