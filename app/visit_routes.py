from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .context import RequestContext, get_context
from .models import (
    AiFieldSuggestion,
    AiTranscriptTurn,
    AiVisitSession,
    MedicalDocument,
    TemplateVersion,
    utcnow,
)
from .real_ai import real_extract_field_suggestions, real_transcribe_and_diarize


class CreateVisitSessionBody(BaseModel):
    document_id: str


class SuggestionDecisionBody(BaseModel):
    value: Any | None = None


def build_visit_router(session_factory) -> APIRouter:
    router = APIRouter(prefix="/v1/doctor/visit-sessions", tags=["visit-sessions"])

    def db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def require_visit(session: Session, ctx: RequestContext, visit_id: str) -> AiVisitSession:
        row = session.scalar(select(AiVisitSession).where(
            AiVisitSession.id == visit_id,
            AiVisitSession.tenant_id == ctx.tenant_id,
            AiVisitSession.branch_id == ctx.branch_id,
        ))
        if not row:
            raise HTTPException(404, "visit session not found")
        return row

    @router.post("", status_code=201)
    def create_visit(body: CreateVisitSessionBody, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        if not ctx.branch_id or not ctx.practitioner_id:
            raise HTTPException(400, "branch and practitioner context required")
        doc = session.scalar(select(MedicalDocument).where(
            MedicalDocument.id == body.document_id,
            MedicalDocument.tenant_id == ctx.tenant_id,
            MedicalDocument.branch_id == ctx.branch_id,
            MedicalDocument.practitioner_id == ctx.practitioner_id,
        ))
        if not doc:
            raise HTTPException(404, "document not found")
        if doc.status != "draft":
            raise HTTPException(409, "document is not editable")
        existing = session.scalar(select(AiVisitSession).where(
            AiVisitSession.document_id == doc.id,
            AiVisitSession.tenant_id == ctx.tenant_id,
            AiVisitSession.status.in_(["recording", "processing", "review"]),
        ))
        if existing:
            return {"data": _serialize_visit(session, existing)}
        visit = AiVisitSession(
            id=str(uuid.uuid4()),
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            patient_id=doc.patient_id,
            practitioner_id=ctx.practitioner_id,
            document_id=doc.id,
            status="recording",
            received_chunk_ids=[],
        )
        session.add(visit)
        session.commit()
        return {"data": _serialize_visit(session, visit)}

    @router.get("/{visit_id}")
    def get_visit(visit_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        visit = require_visit(session, ctx, visit_id)
        return {"data": _serialize_visit(session, visit)}

    @router.post("/{visit_id}/audio")
    async def upload_audio(
        visit_id: str,
        audio: UploadFile = File(...),
        x_chunk_id: str | None = Header(default=None),
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_visit(session, ctx, visit_id)
        if visit.status not in {"recording", "processing"}:
            raise HTTPException(409, "visit is not recording")
        chunk_id = x_chunk_id or str(uuid.uuid4())
        received = list(visit.received_chunk_ids or [])
        if chunk_id in received:
            return {"data": _serialize_visit(session, visit), "duplicate": True}

        raw = await audio.read()
        if not raw:
            raise HTTPException(400, "audio chunk is empty")

        try:
            turns = real_transcribe_and_diarize(raw, audio.content_type or "application/octet-stream")
        except Exception as exc:
            raise HTTPException(503, f"speech pipeline unavailable: {exc}") from exc

        current_sequence = session.scalar(select(func.max(AiTranscriptTurn.sequence_no)).where(
            AiTranscriptTurn.session_id == visit.id
        )) or 0

        new_turn_ids: list[str] = []
        for offset, turn in enumerate(turns, start=1):
            turn_id = str(uuid.uuid4())
            new_turn_ids.append(turn_id)
            session.add(AiTranscriptTurn(
                id=turn_id,
                tenant_id=ctx.tenant_id,
                session_id=visit.id,
                sequence_no=current_sequence + offset,
                speaker=turn.speaker,
                text=turn.text,
                confidence=turn.confidence,
                started_ms=turn.started_ms,
                ended_ms=turn.ended_ms,
            ))

        received.append(chunk_id)
        visit.received_chunk_ids = received
        session.commit()

        _refresh_suggestions(session, visit)
        session.commit()

        return {"data": _serialize_visit(session, visit), "duplicate": False, "new_turn_ids": new_turn_ids}

    @router.post("/{visit_id}/finish")
    def finish_visit(visit_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        visit = require_visit(session, ctx, visit_id)
        if visit.status == "completed":
            return {"data": _serialize_visit(session, visit)}
        _refresh_suggestions(session, visit)
        visit.status = "review"
        visit.ended_at = utcnow()
        session.commit()
        return {"data": _serialize_visit(session, visit)}

    @router.get("/{visit_id}/transcript")
    def transcript(visit_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        visit = require_visit(session, ctx, visit_id)
        turns = session.scalars(select(AiTranscriptTurn).where(
            AiTranscriptTurn.session_id == visit.id
        ).order_by(AiTranscriptTurn.sequence_no)).all()
        return {"data": [_serialize_turn(row) for row in turns]}

    @router.get("/{visit_id}/suggestions")
    def suggestions(visit_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        visit = require_visit(session, ctx, visit_id)
        rows = session.scalars(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == visit.id
        ).order_by(AiFieldSuggestion.field_id)).all()
        return {"data": [_serialize_suggestion(row) for row in rows]}

    @router.post("/{visit_id}/suggestions/{field_id}/accept")
    def accept_suggestion(
        visit_id: str,
        field_id: str,
        body: SuggestionDecisionBody,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_visit(session, ctx, visit_id)
        suggestion = session.scalar(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == visit.id,
            AiFieldSuggestion.field_id == field_id,
        ))
        if not suggestion:
            raise HTTPException(404, "suggestion not found")
        doc = session.get(MedicalDocument, visit.document_id)
        if not doc or doc.status != "draft":
            raise HTTPException(409, "document is not editable")
        values = dict(doc.values or {})
        extracted = suggestion.value_json.get("value") if isinstance(suggestion.value_json, dict) else None
        values[field_id] = body.value if body.value is not None else extracted
        doc.values = values
        suggestion.status = "edited" if body.value is not None else "accepted"
        session.commit()
        return {"data": {"field_id": field_id, "status": suggestion.status, "value": values[field_id]}}

    @router.post("/{visit_id}/suggestions/{field_id}/reject")
    def reject_suggestion(
        visit_id: str,
        field_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_visit(session, ctx, visit_id)
        suggestion = session.scalar(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == visit.id,
            AiFieldSuggestion.field_id == field_id,
        ))
        if not suggestion:
            raise HTTPException(404, "suggestion not found")
        suggestion.status = "rejected"
        session.commit()
        return {"data": {"field_id": field_id, "status": "rejected"}}

    return router


def _refresh_suggestions(session: Session, visit: AiVisitSession) -> None:
    doc = session.get(MedicalDocument, visit.document_id)
    if not doc:
        return
    version = session.get(TemplateVersion, doc.template_version_id)
    if not version:
        return
    turns = session.scalars(select(AiTranscriptTurn).where(
        AiTranscriptTurn.session_id == visit.id
    ).order_by(AiTranscriptTurn.sequence_no)).all()
    serialized_turns = [_serialize_turn(row) for row in turns]
    if not serialized_turns:
        return
    suggestions = real_extract_field_suggestions(version.fields or [], serialized_turns)
    for suggestion in suggestions:
        existing = session.scalar(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == visit.id,
            AiFieldSuggestion.field_id == suggestion.field_id,
        ))
        if existing and existing.status in {"accepted", "edited"}:
            continue
        if existing:
            existing.value_json = suggestion.value_json
            existing.confidence = suggestion.confidence
            existing.evidence_turn_ids = suggestion.evidence_turn_ids
            existing.status = "suggested"
        else:
            session.add(AiFieldSuggestion(
                id=str(uuid.uuid4()),
                tenant_id=visit.tenant_id,
                session_id=visit.id,
                field_id=suggestion.field_id,
                value_json=suggestion.value_json,
                confidence=suggestion.confidence,
                evidence_turn_ids=suggestion.evidence_turn_ids,
                status="suggested",
            ))


def _serialize_turn(row: AiTranscriptTurn) -> dict[str, Any]:
    return {
        "id": row.id,
        "sequence_no": row.sequence_no,
        "speaker": row.speaker,
        "text": row.text,
        "confidence": row.confidence,
        "started_ms": row.started_ms,
        "ended_ms": row.ended_ms,
    }


def _serialize_suggestion(row: AiFieldSuggestion) -> dict[str, Any]:
    return {
        "id": row.id,
        "field_id": row.field_id,
        "value_json": row.value_json,
        "confidence": row.confidence,
        "evidence_turn_ids": row.evidence_turn_ids,
        "status": row.status,
    }


def _serialize_visit(session: Session, row: AiVisitSession) -> dict[str, Any]:
    transcript = session.scalars(select(AiTranscriptTurn).where(
        AiTranscriptTurn.session_id == row.id
    ).order_by(AiTranscriptTurn.sequence_no)).all()
    suggestions = session.scalars(select(AiFieldSuggestion).where(
        AiFieldSuggestion.session_id == row.id
    ).order_by(AiFieldSuggestion.field_id)).all()
    return {
        "id": row.id,
        "document_id": row.document_id,
        "patient_id": row.patient_id,
        "practitioner_id": row.practitioner_id,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "transcript": [_serialize_turn(item) for item in transcript],
        "suggestions": [_serialize_suggestion(item) for item in suggestions],
    }
