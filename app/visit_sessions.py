from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from .ai_visit import ClinicalExtractionClient, ClinicalSuggestion, SpeakerTurn, SpeechPipelineClient, validate_ai_result
from .context import RequestContext, get_context
from .models import AiFieldSuggestion, AiTranscriptTurn, AiVisitSession, MedicalDocument, TemplateVersion, utcnow


class CreateVisitSessionBody(BaseModel):
    document_id: str
    patient_id: str


def register_visit_session_routes(
    app: FastAPI,
    SessionLocal: sessionmaker,
    *,
    speech_client: SpeechPipelineClient | None,
    extraction_client: ClinicalExtractionClient | None,
) -> None:
    def db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def require_session(session: Session, ctx: RequestContext, session_id: str) -> AiVisitSession:
        row = session.scalar(select(AiVisitSession).where(
            AiVisitSession.id == session_id,
            AiVisitSession.tenant_id == ctx.tenant_id,
            AiVisitSession.branch_id == ctx.branch_id,
        ))
        if not row:
            raise HTTPException(404, "visit session not found")
        return row

    def serialize_turns(session: Session, session_id: str) -> list[dict[str, Any]]:
        rows = session.scalars(select(AiTranscriptTurn).where(
            AiTranscriptTurn.session_id == session_id,
        ).order_by(AiTranscriptTurn.sequence_no)).all()
        return [{
            "id": row.id,
            "sequence_no": row.sequence_no,
            "speaker": row.speaker,
            "text": row.text,
            "confidence": row.confidence,
            "started_ms": row.started_ms,
            "ended_ms": row.ended_ms,
        } for row in rows]

    def serialize_suggestions(session: Session, session_id: str) -> list[dict[str, Any]]:
        rows = session.scalars(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == session_id,
        ).order_by(AiFieldSuggestion.field_id)).all()
        return [{
            "id": row.id,
            "field_id": row.field_id,
            "value": (row.value_json or {}).get("value"),
            "confidence": row.confidence,
            "evidence_turn_ids": row.evidence_turn_ids,
            "status": row.status,
        } for row in rows]

    def replace_turns(session: Session, visit: AiVisitSession, turns: list[SpeakerTurn]) -> list[AiTranscriptTurn]:
        session.execute(delete(AiTranscriptTurn).where(AiTranscriptTurn.session_id == visit.id))
        stored: list[AiTranscriptTurn] = []
        for index, turn in enumerate(turns):
            row = AiTranscriptTurn(
                id=str(uuid.uuid4()),
                tenant_id=visit.tenant_id,
                session_id=visit.id,
                sequence_no=index,
                speaker=turn.speaker,
                text=turn.text,
                confidence=turn.confidence,
                started_ms=turn.started_ms,
                ended_ms=turn.ended_ms,
            )
            session.add(row)
            stored.append(row)
        session.flush()
        return stored

    def append_turns(session: Session, visit: AiVisitSession, turns: list[SpeakerTurn]) -> None:
        existing = session.scalars(select(AiTranscriptTurn).where(
            AiTranscriptTurn.session_id == visit.id
        ).order_by(AiTranscriptTurn.sequence_no)).all()
        next_sequence = len(existing)
        for offset, turn in enumerate(turns):
            session.add(AiTranscriptTurn(
                id=str(uuid.uuid4()),
                tenant_id=visit.tenant_id,
                session_id=visit.id,
                sequence_no=next_sequence + offset,
                speaker=turn.speaker,
                text=turn.text,
                confidence=turn.confidence,
                started_ms=turn.started_ms,
                ended_ms=turn.ended_ms,
            ))
        session.flush()

    def current_turn_objects(session: Session, visit_id: str) -> tuple[list[AiTranscriptTurn], list[SpeakerTurn]]:
        rows = session.scalars(select(AiTranscriptTurn).where(
            AiTranscriptTurn.session_id == visit_id,
        ).order_by(AiTranscriptTurn.sequence_no)).all()
        turns = [SpeakerTurn(
            speaker=row.speaker,
            text=row.text,
            confidence=row.confidence,
            started_ms=row.started_ms,
            ended_ms=row.ended_ms,
        ) for row in rows]
        return rows, turns

    def replace_suggestions(
        session: Session,
        visit: AiVisitSession,
        stored_turns: list[AiTranscriptTurn],
        suggestions: list[ClinicalSuggestion],
    ) -> None:
        prior = {
            row.field_id: row
            for row in session.scalars(select(AiFieldSuggestion).where(
                AiFieldSuggestion.session_id == visit.id
            )).all()
        }
        proposed_ids = {s.field_id for s in suggestions}
        for field_id, row in prior.items():
            if row.status == "suggested" and field_id not in proposed_ids:
                session.delete(row)
        for suggestion in suggestions:
            evidence_ids = [
                stored_turns[index].id
                for index in suggestion.evidence_turn_indexes
                if 0 <= index < len(stored_turns)
            ]
            row = prior.get(suggestion.field_id)
            if row and row.status in {"accepted", "edited", "rejected"}:
                continue
            if row is None:
                row = AiFieldSuggestion(
                    id=str(uuid.uuid4()),
                    tenant_id=visit.tenant_id,
                    session_id=visit.id,
                    field_id=suggestion.field_id,
                    value_json={"value": suggestion.value},
                    confidence=suggestion.confidence,
                    evidence_turn_ids=evidence_ids,
                    status="suggested",
                )
                session.add(row)
            else:
                row.value_json = {"value": suggestion.value}
                row.confidence = suggestion.confidence
                row.evidence_turn_ids = evidence_ids

    def extract_suggestions(session: Session, visit: AiVisitSession) -> None:
        if extraction_client is None:
            return
        document = session.get(MedicalDocument, visit.document_id)
        version = session.get(TemplateVersion, document.template_version_id) if document else None
        if not document or not version:
            return
        stored_turns, turns = current_turn_objects(session, visit.id)
        suggestions = extraction_client.extract(
            fields=version.fields or [],
            turns=turns,
            system_values=document.system_values or {},
        )
        validate_ai_result(
            declared_fields=version.fields or [],
            turns=turns,
            suggestions=suggestions,
        )
        replace_suggestions(session, visit, stored_turns, suggestions)

    @app.post("/v1/doctor/visit-sessions", status_code=201)
    def create_visit_session(
        body: CreateVisitSessionBody,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        if not ctx.branch_id or not ctx.practitioner_id:
            raise HTTPException(400, "branch and practitioner context required")
        if speech_client is None or extraction_client is None:
            raise HTTPException(503, "real speech and clinical extraction providers must be configured")
        document = session.scalar(select(MedicalDocument).where(
            MedicalDocument.id == body.document_id,
            MedicalDocument.tenant_id == ctx.tenant_id,
            MedicalDocument.branch_id == ctx.branch_id,
        ))
        if not document:
            raise HTTPException(404, "document not found")
        if document.patient_id != body.patient_id:
            raise HTTPException(400, "document patient mismatch")
        if document.status != "draft":
            raise HTTPException(409, "document is not editable")
        row = AiVisitSession(
            id=str(uuid.uuid4()),
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            patient_id=body.patient_id,
            practitioner_id=ctx.practitioner_id,
            document_id=document.id,
            status="recording",
            received_chunk_ids=[],
        )
        session.add(row)
        session.commit()
        return {"data": {"id": row.id, "status": row.status, "document_id": row.document_id}}

    @app.get("/v1/doctor/visit-sessions/{session_id}")
    def get_visit_session(
        session_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        return {"data": {
            "id": visit.id,
            "status": visit.status,
            "patient_id": visit.patient_id,
            "document_id": visit.document_id,
            "transcript": serialize_turns(session, visit.id),
            "suggestions": serialize_suggestions(session, visit.id),
        }}

    @app.get("/v1/doctor/visit-sessions/{session_id}/transcript")
    def get_transcript(
        session_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        return {"data": serialize_turns(session, visit.id)}

    @app.get("/v1/doctor/visit-sessions/{session_id}/suggestions")
    def get_suggestions(
        session_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        return {"data": serialize_suggestions(session, visit.id)}

    @app.post("/v1/doctor/visit-sessions/{session_id}/audio")
    async def ingest_audio(
        session_id: str,
        chunk_id: str = Form(...),
        audio: UploadFile = File(...),
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        if speech_client is None:
            raise HTTPException(503, "real speech provider is not configured")
        if visit.status != "recording":
            raise HTTPException(409, "visit session is not recording")
        received = list(visit.received_chunk_ids or [])
        if chunk_id in received:
            return {"data": {
                "duplicate": True,
                "transcript": serialize_turns(session, visit.id),
                "suggestions": serialize_suggestions(session, visit.id),
            }}
        turns = speech_client.ingest_chunk(
            session_id=visit.id,
            chunk_id=chunk_id,
            audio=await audio.read(),
            mime_type=audio.content_type or "application/octet-stream",
        )
        validate_ai_result(declared_fields=[], turns=turns, suggestions=[])
        append_turns(session, visit, turns)
        visit.received_chunk_ids = received + [chunk_id]
        extract_suggestions(session, visit)
        session.commit()
        return {"data": {
            "duplicate": False,
            "transcript": serialize_turns(session, visit.id),
            "suggestions": serialize_suggestions(session, visit.id),
        }}

    @app.post("/v1/doctor/visit-sessions/{session_id}/finish")
    def finish_visit_session(
        session_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        if speech_client is None or extraction_client is None:
            raise HTTPException(503, "real AI providers are not configured")
        if visit.status not in {"recording", "processing"}:
            raise HTTPException(409, "visit session cannot be finished")
        visit.status = "processing"
        session.flush()
        final_turns = speech_client.finalize(session_id=visit.id)
        validate_ai_result(declared_fields=[], turns=final_turns, suggestions=[])
        replace_turns(session, visit, final_turns)
        extract_suggestions(session, visit)
        visit.status = "review"
        visit.ended_at = utcnow()
        session.commit()
        return {"data": {
            "id": visit.id,
            "status": visit.status,
            "transcript": serialize_turns(session, visit.id),
            "suggestions": serialize_suggestions(session, visit.id),
        }}

    @app.post("/v1/doctor/visit-sessions/{session_id}/suggestions/{field_id}/accept")
    def accept_suggestion(
        session_id: str,
        field_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        suggestion = session.scalar(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == visit.id,
            AiFieldSuggestion.field_id == field_id,
        ))
        if not suggestion:
            raise HTTPException(404, "suggestion not found")
        document = session.get(MedicalDocument, visit.document_id)
        if not document or document.status != "draft":
            raise HTTPException(409, "document is not editable")
        values = dict(document.values or {})
        values[field_id] = (suggestion.value_json or {}).get("value")
        document.values = values
        suggestion.status = "accepted"
        session.commit()
        return {"data": {"field_id": field_id, "status": suggestion.status, "value": values[field_id]}}

    @app.post("/v1/doctor/visit-sessions/{session_id}/suggestions/{field_id}/reject")
    def reject_suggestion(
        session_id: str,
        field_id: str,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        visit = require_session(session, ctx, session_id)
        suggestion = session.scalar(select(AiFieldSuggestion).where(
            AiFieldSuggestion.session_id == visit.id,
            AiFieldSuggestion.field_id == field_id,
        ))
        if not suggestion:
            raise HTTPException(404, "suggestion not found")
        suggestion.status = "rejected"
        session.commit()
        return {"data": {"field_id": field_id, "status": "rejected"}}
