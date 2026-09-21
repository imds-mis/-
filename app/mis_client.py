from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MisClient:
    def __init__(self, base_url: str, token: str | None = None, timeout_seconds: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def _get(self, path: str, query: dict[str, str | None] | None = None) -> dict[str, Any]:
        suffix = ""
        if query:
            filtered = {k: v for k, v in query.items() if v is not None and v != ""}
            if filtered:
                suffix = "?" + urlencode(filtered)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = self.token if self.token.lower().startswith("bearer ") else f"Bearer {self.token}"
        req = Request(f"{self.base_url}{path}{suffix}", headers=headers, method="GET")
        with urlopen(req, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("MIS API returned non-object JSON")
        return data

    def list_patients(self, branch_id: str | None = None) -> list[dict[str, Any]]:
        data = self._get("/api/products/mis/v1/patients", {"branch_id": branch_id})
        rows = data.get("data")
        if not isinstance(rows, list):
            raise ValueError("MIS patients response has no data list")
        return [row for row in rows if isinstance(row, dict)]

    def get_patient(self, patient_id: str, branch_id: str | None = None) -> dict[str, Any]:
        data = self._get(f"/api/products/mis/v1/patients/{patient_id}", {"branch_id": branch_id})
        row = data.get("data")
        if not isinstance(row, dict):
            raise ValueError("MIS patient response has no data object")
        return row

    def list_practitioners(self, branch_id: str | None = None) -> list[dict[str, Any]]:
        data = self._get("/api/products/mis/v1/practitioners", {"branch_id": branch_id})
        rows = data.get("data")
        if not isinstance(rows, list):
            raise ValueError("MIS practitioners response has no data list")
        return [row for row in rows if isinstance(row, dict)]
