from __future__ import annotations

import json
from typing import Any, Callable, Iterable
from urllib.request import Request, urlopen

from .domain import field_supports_dictation


def transcribe_for_field(fields: Iterable[dict[str, Any]], field_id: str, audio: bytes, content_type: str, stt: Callable[[bytes, str], str]) -> dict[str, Any]:
    field = next((f for f in fields if f.get("id") == field_id), None)
    if field is None:
        raise ValueError("unknown field")
    if not field_supports_dictation(field):
        raise ValueError("dictation is allowed only for text fields")
    transcript = stt(audio, content_type).strip()
    return {"field_id": field_id, "transcript": transcript, "draft": True}


def make_http_stt(url: str, timeout_seconds: int = 60) -> Callable[[bytes, str], str]:
    def transcribe(audio: bytes, content_type: str) -> str:
        request = Request(url, data=audio, headers={"Content-Type": content_type, "Accept": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = data.get("text") or data.get("transcript")
        if not isinstance(text, str):
            raise ValueError("STT response must contain text or transcript")
        return text
    return transcribe
