from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .catalogs import parse_icd_csv
from .context import RequestContext, get_context
from .domain import template_is_eligible
from .models import Base, DoctorProfile, Icd10Code, MedicalDocument, ProtocolVersion, Template, TemplateAssignment, TemplateVersion, utcnow
from .qr_tokens import create_signed_token, token_hash, verify_signed_token
from .rendering import convert_docx_to_pdf, render_docx
from .speech import make_http_stt, transcribe_for_field
from .storage import LocalStorage
from .template_inspection import inspect_docx_fields
from .ai_visit import ClinicalExtractionClient, SpeechPipelineClient
from .upstream import MisUpstreamClient
from .visit_sessions import register_visit_session_routes


class CreateDocumentBody(BaseModel):
    template_id: str
    patient_id: str
    encounter_id: str | None = None
    visit_type: str | None = None
    system_values: dict[str, Any] = Field(default_factory=dict)


class UpdateFieldsBody(BaseModel):
    values: dict[str, Any]


class DoctorProfileBody(BaseModel):
    practitioner_id: str
    display_name: str | None = None
    specialty_codes: list[str] = Field(default_factory=list)


class ProtocolBody(BaseModel):
    title: str
    version: str
    source_org: str | None = None
    source_url: str | None = None
    status: str = "draft"
    icd_codes: list[str] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)
    effective_from: str | None = None
    effective_to: str | None = None


def create_app(
    *,
    database_url: str,
    storage_root: Path,
    qr_secret: str,
    public_base_url: str,
    stt_url: str | None,
    stt_callable: Callable[[bytes, str], str] | None = None,
    mis_upstream_url: str | None = None,
    mis_auth_token: str | None = None,
    speech_pipeline_url: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)
    storage = LocalStorage(storage_root)
    effective_stt = stt_callable or (make_http_stt(stt_url) if stt_url else None)
    upstream_client = (
        MisUpstreamClient(mis_upstream_url, mis_auth_token)
        if mis_upstream_url and mis_auth_token
        else None
    )
    speech_client = SpeechPipelineClient(speech_pipeline_url) if speech_pipeline_url else None
    extraction_client = (
        ClinicalExtractionClient(
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model,
        )
        if llm_base_url and llm_api_key and llm_model
        else None
    )

    app = FastAPI(title="IMDS Medical Document Service", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    app.state.storage = storage
    app.state.qr_secret = qr_secret
    app.state.public_base_url = public_base_url.rstrip("/")
    app.state.stt = effective_stt
    app.state.upstream = upstream_client
    app.state.speech_client = speech_client
    app.state.extraction_client = extraction_client

    register_visit_session_routes(
        app,
        SessionLocal,
        speech_client=speech_client,
        extraction_client=extraction_client,
    )

    def db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def require_document(session: Session, ctx: RequestContext, document_id: str) -> MedicalDocument:
        doc = session.scalar(select(MedicalDocument).where(
            MedicalDocument.id == document_id,
            MedicalDocument.tenant_id == ctx.tenant_id,
            MedicalDocument.branch_id == ctx.branch_id,
        ))
        if not doc:
            raise HTTPException(404, "document not found")
        return doc

    def make_document_token(doc: MedicalDocument) -> str:
        return create_signed_token(
            app.state.qr_secret,
            {
                "document_public_id": doc.public_id,
                "document_version_id": doc.id,
                "iat": int(doc.created_at.timestamp()) if doc.created_at else 0,
                "nonce": doc.id,
            },
        )

    def response_payload(doc: MedicalDocument, token: str | None = None) -> dict[str, Any]:
        return {
            "id": doc.id,
            "status": doc.status,
            "sha256": doc.sha256,
            "pdf_download_url": f"/v1/doctor/documents/{doc.id}/pdf",
            "docx_download_url": f"/v1/doctor/documents/{doc.id}/docx",
            "verification_url": f"{app.state.public_base_url}/v1/public/documents/{token}" if token else None,
        }

    @app.get("/healthz")
    def health():
        return {"status": "ok", "service": "medical-document-service"}

    @app.get("/v1/integrations/mis/patients")
    def upstream_patients(
        ctx: RequestContext = Depends(get_context),
    ):
        if upstream_client is None:
            raise HTTPException(503, "real MIS upstream is not configured")
        if not ctx.branch_id:
            raise HTTPException(400, "branch context required")
        try:
            data = upstream_client.list_patients(ctx.branch_id)
        except Exception as exc:
            raise HTTPException(502, "MIS upstream patient request failed") from exc
        return {"data": data}

    @app.get("/v1/integrations/mis/practitioners")
    def upstream_practitioners(
        ctx: RequestContext = Depends(get_context),
    ):
        if upstream_client is None:
            raise HTTPException(503, "real MIS upstream is not configured")
        if not ctx.branch_id:
            raise HTTPException(400, "branch context required")
        try:
            data = upstream_client.list_practitioners(ctx.branch_id)
        except Exception as exc:
            raise HTTPException(502, "MIS upstream practitioner request failed") from exc
        return {"data": data}

    @app.get("/v1/integrations/mis/patients/{patient_id}")
    def upstream_patient(
        patient_id: str,
        ctx: RequestContext = Depends(get_context),
    ):
        if upstream_client is None:
            raise HTTPException(503, "real MIS upstream is not configured")
        if not ctx.branch_id:
            raise HTTPException(400, "branch context required")
        try:
            data = upstream_client.get_patient(patient_id, ctx.branch_id)
        except Exception as exc:
            raise HTTPException(502, "MIS upstream patient request failed") from exc
        if not data:
            raise HTTPException(404, "patient not found")
        return {"data": data}

    @app.post("/v1/admin/doctor-profiles", status_code=201)
    def create_doctor_profile(
        body: DoctorProfileBody,
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        if not body.specialty_codes:
            raise HTTPException(400, "at least one specialty code is required")
        existing = session.scalar(select(DoctorProfile).where(
            DoctorProfile.tenant_id == ctx.tenant_id,
            DoctorProfile.practitioner_id == body.practitioner_id,
        ))
        normalized = sorted({code.strip().upper() for code in body.specialty_codes if code.strip()})
        if existing:
            existing.display_name = body.display_name
            existing.specialty_codes = normalized
            existing.branch_id = ctx.branch_id
            existing.active = True
            profile = existing
        else:
            profile = DoctorProfile(
                id=str(uuid.uuid4()),
                tenant_id=ctx.tenant_id,
                branch_id=ctx.branch_id,
                practitioner_id=body.practitioner_id,
                display_name=body.display_name,
                specialty_codes=normalized,
                active=True,
            )
            session.add(profile)
        session.commit()
        return {"data": {
            "id": profile.id,
            "practitioner_id": profile.practitioner_id,
            "display_name": profile.display_name,
            "specialty_codes": profile.specialty_codes,
            "active": profile.active,
        }}

    @app.get("/v1/admin/doctor-profiles")
    def list_doctor_profiles(
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        rows = session.scalars(select(DoctorProfile).where(
            DoctorProfile.tenant_id == ctx.tenant_id,
            DoctorProfile.active.is_(True),
        ).order_by(DoctorProfile.display_name, DoctorProfile.practitioner_id)).all()
        return {"data": [{
            "id": row.id,
            "practitioner_id": row.practitioner_id,
            "display_name": row.display_name,
            "specialty_codes": row.specialty_codes,
            "branch_id": row.branch_id,
        } for row in rows]}

    @app.get("/v1/admin/templates")
    def list_templates(
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        templates = session.scalars(
            select(Template)
            .where(Template.tenant_id == ctx.tenant_id)
            .order_by(Template.created_at.desc())
        ).all()
        data = []
        for template in templates:
            versions = session.scalars(
                select(TemplateVersion)
                .where(
                    TemplateVersion.tenant_id == ctx.tenant_id,
                    TemplateVersion.template_id == template.id,
                )
                .order_by(TemplateVersion.version.desc())
            ).all()
            assignments = session.scalars(
                select(TemplateAssignment).where(
                    TemplateAssignment.tenant_id == ctx.tenant_id,
                    TemplateAssignment.template_id == template.id,
                )
            ).all()
            data.append({
                "id": template.id,
                "name": template.name,
                "active": template.active,
                "created_at": template.created_at,
                "versions": [{
                    "id": version.id,
                    "version": version.version,
                    "status": version.status,
                    "fields": version.fields,
                } for version in versions],
                "assignments": [{
                    "specialty_code": a.specialty_code,
                    "branch_id": a.branch_id,
                    "practitioner_id": a.practitioner_id,
                    "visit_type": a.visit_type,
                } for a in assignments],
            })
        return {"data": data}

    @app.post("/v1/admin/templates/inspect")
    async def inspect_template(
        file: UploadFile = File(...),
        ctx: RequestContext = Depends(get_context),
    ):
        if not file.filename or not file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "DOCX required")
        try:
            fields = inspect_docx_fields(await file.read())
        except Exception as exc:
            raise HTTPException(400, "unable to inspect DOCX") from exc
        return {"data": {"filename": file.filename, "fields": fields}}

    @app.post("/v1/admin/templates", status_code=201)
    async def create_template(
        name: str = Form(...),
        fields_json: str = Form("[]"),
        assignments_json: str = Form("[]"),
        file: UploadFile = File(...),
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        if not file.filename or not file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "DOCX required")
        try:
            fields = json.loads(fields_json)
            assignments = json.loads(assignments_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "invalid JSON metadata") from exc
        template_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        source_key = f"{ctx.tenant_id}/templates/{template_id}/v1/source.docx"
        storage.write(source_key, await file.read())
        template = Template(id=template_id, tenant_id=ctx.tenant_id, name=name, active=True)
        version = TemplateVersion(id=version_id, tenant_id=ctx.tenant_id, template_id=template_id, version=1, status="draft", source_key=source_key, fields=fields)
        session.add_all([template, version])
        for assignment in assignments:
            session.add(TemplateAssignment(
                id=str(uuid.uuid4()),
                tenant_id=ctx.tenant_id,
                template_id=template_id,
                specialty_code=assignment.get("specialty_code"),
                branch_id=assignment.get("branch_id"),
                practitioner_id=assignment.get("practitioner_id"),
                visit_type=assignment.get("visit_type"),
            ))
        session.commit()
        return {"data": {"id": template.id, "name": template.name, "version": 1, "status": "draft"}}

    @app.post("/v1/admin/templates/{template_id}/versions", status_code=201)
    async def create_template_version(
        template_id: str,
        fields_json: str = Form("[]"),
        file: UploadFile = File(...),
        ctx: RequestContext = Depends(get_context),
        session: Session = Depends(db),
    ):
        template = session.scalar(select(Template).where(
            Template.id == template_id,
            Template.tenant_id == ctx.tenant_id,
        ))
        if not template:
            raise HTTPException(404, "template not found")
        if not file.filename or not file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "DOCX required")
        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "invalid JSON metadata") from exc
        latest = session.scalars(select(TemplateVersion).where(
            TemplateVersion.template_id == template_id,
            TemplateVersion.tenant_id == ctx.tenant_id,
        ).order_by(TemplateVersion.version.desc())).first()
        next_version = (latest.version if latest else 0) + 1
        version_id = str(uuid.uuid4())
        source_key = f"{ctx.tenant_id}/templates/{template_id}/v{next_version}/source.docx"
        storage.write(source_key, await file.read())
        version = TemplateVersion(
            id=version_id,
            tenant_id=ctx.tenant_id,
            template_id=template_id,
            version=next_version,
            status="draft",
            source_key=source_key,
            fields=fields,
        )
        session.add(version)
        session.commit()
        return {"data": {"id": version.id, "template_id": template_id, "version": next_version, "status": "draft"}}

    @app.post("/v1/admin/templates/{template_id}/disable")
    def disable_template(template_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        template = session.scalar(select(Template).where(
            Template.id == template_id,
            Template.tenant_id == ctx.tenant_id,
        ))
        if not template:
            raise HTTPException(404, "template not found")
        template.active = False
        session.commit()
        return {"data": {"id": template.id, "active": False}}

    @app.post("/v1/admin/templates/{template_id}/publish")
    def publish_template(template_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        template = session.scalar(select(Template).where(Template.id == template_id, Template.tenant_id == ctx.tenant_id))
        if not template:
            raise HTTPException(404, "template not found")
        version = session.scalars(select(TemplateVersion).where(
            TemplateVersion.template_id == template_id,
            TemplateVersion.tenant_id == ctx.tenant_id,
        ).order_by(TemplateVersion.version.desc())).first()
        if not version:
            raise HTTPException(409, "template has no version")
        version.status = "published"
        session.commit()
        return {"data": {"id": template_id, "version": version.version, "status": version.status}}

    @app.get("/v1/doctor/templates")
    def eligible_templates(visit_type: str | None = None, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        if not ctx.practitioner_id:
            raise HTTPException(400, "practitioner context required")
        profile = session.scalar(select(DoctorProfile).where(
            DoctorProfile.tenant_id == ctx.tenant_id,
            DoctorProfile.practitioner_id == ctx.practitioner_id,
            DoctorProfile.active.is_(True),
        ))
        profile_specialties = profile.specialty_codes if profile else []
        templates = session.scalars(select(Template).where(Template.tenant_id == ctx.tenant_id, Template.active.is_(True))).all()
        out = []
        for template in templates:
            latest = session.scalars(select(TemplateVersion).where(
                TemplateVersion.template_id == template.id,
                TemplateVersion.status == "published",
            ).order_by(TemplateVersion.version.desc())).first()
            if not latest:
                continue
            assignments = session.scalars(select(TemplateAssignment).where(
                TemplateAssignment.template_id == template.id,
                TemplateAssignment.tenant_id == ctx.tenant_id,
            )).all()
            rows = [{"specialty_code": a.specialty_code, "branch_id": a.branch_id, "practitioner_id": a.practitioner_id, "visit_type": a.visit_type} for a in assignments]
            eligible = False
            candidate_specialties = profile_specialties or ([ctx.specialty_code] if ctx.specialty_code else [])
            if not rows:
                eligible = True
            else:
                for specialty in candidate_specialties or [None]:
                    if template_is_eligible(rows, specialty_code=specialty, branch_id=ctx.branch_id, practitioner_id=ctx.practitioner_id, visit_type=visit_type):
                        eligible = True
                        break
            if not eligible:
                continue
            out.append({"id": template.id, "name": template.name, "version": latest.version, "fields": latest.fields})
        return {"data": out}

    @app.post("/v1/doctor/documents", status_code=201)
    def create_document(body: CreateDocumentBody, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        if not ctx.branch_id or not ctx.practitioner_id:
            raise HTTPException(400, "branch and practitioner context required")
        template = session.scalar(select(Template).where(Template.id == body.template_id, Template.tenant_id == ctx.tenant_id, Template.active.is_(True)))
        if not template:
            raise HTTPException(404, "template not found")
        version = session.scalars(select(TemplateVersion).where(
            TemplateVersion.template_id == template.id,
            TemplateVersion.tenant_id == ctx.tenant_id,
            TemplateVersion.status == "published",
        ).order_by(TemplateVersion.version.desc())).first()
        if not version:
            raise HTTPException(409, "template not published")
        assignments = session.scalars(select(TemplateAssignment).where(
            TemplateAssignment.template_id == template.id,
            TemplateAssignment.tenant_id == ctx.tenant_id,
        )).all()
        rows = [{"specialty_code": a.specialty_code, "branch_id": a.branch_id, "practitioner_id": a.practitioner_id, "visit_type": a.visit_type} for a in assignments]
        profile = session.scalar(select(DoctorProfile).where(
            DoctorProfile.tenant_id == ctx.tenant_id,
            DoctorProfile.practitioner_id == ctx.practitioner_id,
            DoctorProfile.active.is_(True),
        ))
        candidate_specialties = profile.specialty_codes if profile else ([ctx.specialty_code] if ctx.specialty_code else [])
        eligible = not rows
        if rows:
            for specialty in candidate_specialties or [None]:
                if template_is_eligible(
                    rows,
                    specialty_code=specialty,
                    branch_id=ctx.branch_id,
                    practitioner_id=ctx.practitioner_id,
                    visit_type=body.visit_type,
                ):
                    eligible = True
                    break
        if not eligible:
            raise HTTPException(403, "template not eligible")
        doc = MedicalDocument(
            id=str(uuid.uuid4()),
            public_id=str(uuid.uuid4()),
            tenant_id=ctx.tenant_id,
            branch_id=ctx.branch_id,
            patient_id=body.patient_id,
            encounter_id=body.encounter_id,
            practitioner_id=ctx.practitioner_id,
            template_id=template.id,
            template_version_id=version.id,
            status="draft",
            values={},
            system_values=body.system_values,
        )
        session.add(doc)
        session.commit()
        return {"data": {"id": doc.id, "public_id": doc.public_id, "status": doc.status, "template_version": version.version, "values": doc.values}}

    @app.patch("/v1/doctor/documents/{document_id}/fields")
    def update_fields(document_id: str, body: UpdateFieldsBody, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        doc = require_document(session, ctx, document_id)
        if doc.status != "draft":
            raise HTTPException(409, "finalized document is immutable")
        version = session.get(TemplateVersion, doc.template_version_id)
        allowed = {field.get("id") for field in (version.fields or [])}
        unknown = set(body.values) - allowed
        if unknown:
            raise HTTPException(400, f"unknown fields: {sorted(unknown)}")
        values = dict(doc.values or {})
        values.update(body.values)
        doc.values = values
        session.commit()
        return {"data": {"id": doc.id, "status": doc.status, "values": doc.values}}

    @app.post("/v1/doctor/documents/{document_id}/speech/{field_id}")
    async def speech(document_id: str, field_id: str, audio: UploadFile = File(...), ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        doc = require_document(session, ctx, document_id)
        if doc.status != "draft":
            raise HTTPException(409, "finalized document is immutable")
        if app.state.stt is None:
            raise HTTPException(503, "speech-to-text is not configured")
        version = session.get(TemplateVersion, doc.template_version_id)
        try:
            result = transcribe_for_field(version.fields or [], field_id, await audio.read(), audio.content_type or "application/octet-stream", app.state.stt)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"data": result}

    @app.post("/v1/admin/icd10/import", status_code=201)
    async def import_icd(version: str = Form(...), source: str = Form(...), file: UploadFile = File(...), ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        rows = parse_icd_csv(await file.read())
        for row in rows:
            existing = session.scalar(select(Icd10Code).where(
                Icd10Code.tenant_id == ctx.tenant_id,
                Icd10Code.code == row["code"],
                Icd10Code.version == version,
            ))
            if existing:
                existing.title = row["title"]
                existing.source = source
                existing.active = True
            else:
                session.add(Icd10Code(id=str(uuid.uuid4()), tenant_id=ctx.tenant_id, code=row["code"], title=row["title"], version=version, source=source, active=True))
        session.commit()
        return {"data": {"imported": len(rows), "version": version, "source": source}}

    @app.get("/v1/doctor/icd10")
    def search_icd(q: str = Query(min_length=1), ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        query_text = q.strip().casefold()
        rows = session.scalars(select(Icd10Code).where(
            Icd10Code.tenant_id == ctx.tenant_id,
            Icd10Code.active.is_(True),
        )).all()
        matched = [r for r in rows if query_text in r.code.casefold() or query_text in r.title.casefold()][:50]
        return {"data": [{"code": r.code, "title": r.title, "version": r.version, "source": r.source} for r in matched]}

    @app.post("/v1/admin/protocols", status_code=201)
    def create_protocol(body: ProtocolBody, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        if body.status not in {"draft", "published", "archived"}:
            raise HTTPException(400, "invalid protocol status")
        row = ProtocolVersion(
            id=str(uuid.uuid4()),
            tenant_id=ctx.tenant_id,
            title=body.title,
            version=body.version,
            source_org=body.source_org,
            source_url=body.source_url,
            status=body.status,
            icd_codes=[code.upper() for code in body.icd_codes],
            items=body.items,
            effective_from=body.effective_from,
            effective_to=body.effective_to,
        )
        session.add(row)
        session.commit()
        return {"data": {"id": row.id, "title": row.title, "version": row.version, "status": row.status}}

    @app.get("/v1/doctor/protocols")
    def protocols(icd_code: str | None = None, q: str | None = None, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        rows = session.scalars(select(ProtocolVersion).where(
            ProtocolVersion.tenant_id == ctx.tenant_id,
            ProtocolVersion.status == "published",
        )).all()
        out = []
        for row in rows:
            if icd_code and icd_code.upper() not in (row.icd_codes or []):
                continue
            if q and q.casefold() not in row.title.casefold():
                continue
            out.append({"id": row.id, "title": row.title, "version": row.version, "source_org": row.source_org, "source_url": row.source_url, "icd_codes": row.icd_codes, "items": row.items})
        return {"data": out}

    @app.post("/v1/doctor/documents/{document_id}/finalize")
    def finalize(document_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        doc = require_document(session, ctx, document_id)
        token = make_document_token(doc)
        if doc.status == "finalized":
            return {"data": response_payload(doc, token)}
        version = session.get(TemplateVersion, doc.template_version_id)
        if not version or version.status != "published":
            raise HTTPException(409, "template version is not published")
        verification_url = f"{app.state.public_base_url}/v1/public/documents/{token}"
        values = dict(doc.system_values or {})
        values.update(doc.values or {})
        docx_key = f"{doc.tenant_id}/documents/{doc.id}/final.docx"
        pdf_key = f"{doc.tenant_id}/documents/{doc.id}/final.pdf"
        with tempfile.TemporaryDirectory() as td:
            rendered_docx = Path(td) / "final.docx"
            rendered_pdf = Path(td) / "final.pdf"
            render_docx(storage.path(version.source_key), rendered_docx, values, verification_url)
            convert_docx_to_pdf(rendered_docx, rendered_pdf)
            docx_bytes = rendered_docx.read_bytes()
            pdf_bytes = rendered_pdf.read_bytes()
        storage.write(docx_key, docx_bytes)
        storage.write(pdf_key, pdf_bytes)
        doc.final_docx_key = docx_key
        doc.final_pdf_key = pdf_key
        doc.sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        doc.qr_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        doc.status = "finalized"
        doc.finalized_at = utcnow()
        session.commit()
        return {"data": response_payload(doc, token)}

    @app.get("/v1/doctor/documents/{document_id}/pdf")
    def download_pdf(document_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        doc = require_document(session, ctx, document_id)
        if doc.status != "finalized" or not doc.final_pdf_key:
            raise HTTPException(409, "document not finalized")
        return FileResponse(storage.path(doc.final_pdf_key), media_type="application/pdf", filename=f"{doc.id}.pdf")

    @app.get("/v1/doctor/documents/{document_id}/docx")
    def download_docx(document_id: str, ctx: RequestContext = Depends(get_context), session: Session = Depends(db)):
        doc = require_document(session, ctx, document_id)
        if doc.status != "finalized" or not doc.final_docx_key:
            raise HTTPException(409, "document not finalized")
        return FileResponse(storage.path(doc.final_docx_key), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=f"{doc.id}.docx")

    @app.get("/v1/public/documents/{token:path}")
    def public_document(token: str, session: Session = Depends(db)):
        try:
            payload = verify_signed_token(app.state.qr_secret, token)
        except ValueError as exc:
            raise HTTPException(404, "invalid verification token") from exc
        doc = session.scalar(select(MedicalDocument).where(
            MedicalDocument.public_id == payload.get("document_public_id"),
            MedicalDocument.id == payload.get("document_version_id"),
        ))
        if not doc or doc.status != "finalized" or doc.qr_revoked or not doc.final_pdf_key:
            raise HTTPException(404, "document not available")
        if not doc.qr_token_hash or token_hash(token) != doc.qr_token_hash:
            raise HTTPException(404, "document not available")
        pdf_path = storage.path(doc.final_pdf_key)
        if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != doc.sha256:
            raise HTTPException(409, "stored document integrity check failed")
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{doc.public_id}.pdf")

    return app
