from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class MisUpstreamClient:
    base_url: str
    bearer_token: str
    timeout_seconds: int = 20

    def patient_list_url(self, branch_id: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/products/mis/v1/patients?{urlencode({'branch_id': branch_id})}"

    def practitioner_list_url(self, branch_id: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/products/mis/v1/practitioners?{urlencode({'branch_id': branch_id})}"

    def patient_url(self, patient_id: str, branch_id: str) -> str:
        return (
            f"{self.base_url.rstrip('/')}/api/products/mis/v1/patients/{patient_id}"
            f"?{urlencode({'branch_id': branch_id})}"
        )

    def _get(self, url: str) -> dict:
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_patients(self, branch_id: str) -> list[dict]:
        return list(self._get(self.patient_list_url(branch_id)).get("data") or [])

    def list_practitioners(self, branch_id: str) -> list[dict]:
        return list(self._get(self.practitioner_list_url(branch_id)).get("data") or [])

    def get_patient(self, patient_id: str, branch_id: str) -> dict:
        return dict(self._get(self.patient_url(patient_id, branch_id)).get("data") or {})
