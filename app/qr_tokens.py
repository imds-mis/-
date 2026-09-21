from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Mapping


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_signed_token(secret: str, payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.setdefault("iat", int(time.time()))
    body.setdefault("nonce", secrets.token_urlsafe(16))
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64(raw)
    sig = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64(sig)}"


def verify_signed_token(secret: str, token: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("invalid token") from exc
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    try:
        supplied = _unb64(signature)
    except Exception as exc:
        raise ValueError("invalid token") from exc
    if not hmac.compare_digest(expected, supplied):
        raise ValueError("invalid token signature")
    try:
        payload = json.loads(_unb64(encoded).decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid token payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid token payload")
    return payload


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
