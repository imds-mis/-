from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    source_key: Mapped[str] = mapped_column(Text)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TemplateAssignment(Base):
    __tablename__ = "template_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"), index=True)
    specialty_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    branch_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    practitioner_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    visit_type: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MedicalDocument(Base):
    __tablename__ = "medical_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    branch_id: Mapped[str] = mapped_column(String(100), index=True)
    patient_id: Mapped[str] = mapped_column(String(100), index=True)
    encounter_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    practitioner_id: Mapped[str] = mapped_column(String(100), index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"))
    template_version_id: Mapped[str] = mapped_column(ForeignKey("template_versions.id"))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    system_values: Mapped[dict] = mapped_column(JSON, default=dict)
    final_docx_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_pdf_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qr_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qr_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Icd10Code(Base):
    __tablename__ = "icd10_codes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(1000), index=True)
    locale: Mapped[str] = mapped_column(String(20), default="ru")
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProtocolVersion(Base):
    __tablename__ = "protocol_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(1000))
    version: Mapped[str] = mapped_column(String(100))
    source_org: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    icd_codes: Mapped[list] = mapped_column(JSON, default=list)
    items: Mapped[list] = mapped_column(JSON, default=list)
    effective_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class AiVisitSession(Base):
    __tablename__ = "ai_visit_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    branch_id: Mapped[str] = mapped_column(String(100), index=True)
    patient_id: Mapped[str] = mapped_column(String(100), index=True)
    practitioner_id: Mapped[str] = mapped_column(String(100), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("medical_documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="recording")
    received_chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiTranscriptTurn(Base):
    __tablename__ = "ai_transcript_turns"
    __table_args__ = (UniqueConstraint("session_id", "sequence_no"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_visit_sessions.id"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    started_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AiFieldSuggestion(Base):
    __tablename__ = "ai_field_suggestions"
    __table_args__ = (UniqueConstraint("session_id", "field_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_visit_sessions.id"), index=True)
    field_id: Mapped[str] = mapped_column(String(200))
    value_json: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    evidence_turn_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="suggested")
