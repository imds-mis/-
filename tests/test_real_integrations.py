from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai_visit import ClinicalSuggestion, SpeakerTurn, validate_ai_result
from app.main import create_app
from app.upstream import MisUpstreamClient


def test_upstream_client_builds_real_mis_patient_url():
    client = MisUpstreamClient(
        base_url="https://mis.imds.kz",
        bearer_token="secret",
        timeout_seconds=10,
    )
    assert client.patient_list_url("11111111-1111-1111-1111-111111111111") == (
        "https://mis.imds.kz/api/products/mis/v1/patients"
        "?branch_id=11111111-1111-1111-1111-111111111111"
    )


def test_ai_result_rejects_undeclared_field():
    with pytest.raises(ValueError, match="undeclared template field"):
        validate_ai_result(
            declared_fields=[{"id": "complaints", "type": "textarea"}],
            turns=[
                SpeakerTurn(
                    speaker="patient",
                    text="Боль два дня",
                    confidence=0.95,
                )
            ],
            suggestions=[
                ClinicalSuggestion(
                    field_id="diagnosis",
                    value="N80",
                    confidence=0.9,
                    evidence_turn_indexes=[0],
                )
            ],
        )


def test_visit_session_requires_real_ai_provider(tmp_path: Path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        storage_root=tmp_path / "storage",
        qr_secret="secret",
        public_base_url="http://testserver",
        stt_url=None,
        mis_upstream_url="https://mis.imds.kz",
        mis_auth_token="real-token",
        speech_pipeline_url=None,
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
    )
    client = TestClient(app)

    headers = {
        "X-Tenant-ID": "t1",
        "X-User-ID": "u1",
        "X-Branch-ID": "b1",
        "X-Practitioner-ID": "p1",
        "X-Specialty-Code": "GYNE",
    }

    response = client.post(
        "/v1/doctor/visit-sessions",
        headers=headers,
        json={
            "document_id": "00000000-0000-0000-0000-000000000000",
            "patient_id": "patient-real",
        },
    )
    assert response.status_code in {404, 503}
    if response.status_code == 503:
        assert "configured" in response.json()["detail"].lower()


def test_real_data_proxy_endpoints_registered(tmp_path: Path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        storage_root=tmp_path / "storage",
        qr_secret="secret",
        public_base_url="http://testserver",
        stt_url=None,
        mis_upstream_url="https://mis.imds.kz",
        mis_auth_token="real-token",
        speech_pipeline_url="http://speech:9000",
        llm_base_url="http://llm:8000/v1",
        llm_api_key="key",
        llm_model="model",
    )

    routes = {(route.path, ",".join(sorted(route.methods or []))) for route in app.routes}
    assert any(path == "/v1/integrations/mis/patients" for path, _ in routes)
    assert any(path == "/v1/integrations/mis/practitioners" for path, _ in routes)
    assert any(path == "/v1/doctor/visit-sessions" for path, _ in routes)
