from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .context import RequestContext, get_context
from .mis_client import MisClient


def build_integration_router(mis_client: MisClient | None) -> APIRouter:
    router = APIRouter(prefix="/v1/integrations/mis", tags=["mis-integration"])

    def require_client() -> MisClient:
        if mis_client is None:
            raise HTTPException(503, "MIS_API_BASE_URL is not configured")
        return mis_client

    @router.get("/status")
    def status():
        return {"data": {"configured": mis_client is not None}}

    @router.get("/patients")
    def patients(ctx: RequestContext = Depends(get_context)):
        client = require_client()
        try:
            return {"data": client.list_patients(ctx.branch_id)}
        except Exception as exc:
            raise HTTPException(502, f"MIS patients request failed: {exc}") from exc

    @router.get("/patients/{patient_id}")
    def patient(patient_id: str, ctx: RequestContext = Depends(get_context)):
        client = require_client()
        try:
            return {"data": client.get_patient(patient_id, ctx.branch_id)}
        except Exception as exc:
            raise HTTPException(502, f"MIS patient request failed: {exc}") from exc

    @router.get("/practitioners")
    def practitioners(ctx: RequestContext = Depends(get_context)):
        client = require_client()
        try:
            return {"data": client.list_practitioners(ctx.branch_id)}
        except Exception as exc:
            raise HTTPException(502, f"MIS practitioners request failed: {exc}") from exc

    return router
