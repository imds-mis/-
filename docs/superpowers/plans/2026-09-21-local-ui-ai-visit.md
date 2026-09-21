# Local UI + AI Visit Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `imds-mis/-` runnable locally with one Docker Compose command, exposing Settings/Templates and Doctor Cabinet with real AI visit capture.

**Architecture:** Keep FastAPI as the backend and add visit-session APIs plus a deterministic real AI adapter. Add a React/Vite frontend with two routes, served by its own container, and a PostgreSQL service. The frontend talks to the API through `VITE_API_BASE_URL`; local context headers emulate authenticated MIS context only in Real mode.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, PostgreSQL, React, Vite, TypeScript, Vitest, Docker Compose, LibreOffice.

**Spec:** `docs/specs/2026-09-21-local-ui-ai-visit-design.md`

## Global Constraints

- No Cloudflare or Supabase.
- `docker compose up --build` must start the whole local real-data run.
- Settings/Templates and Doctor Cabinet are the two primary workspaces.
- AI results remain suggestions until the doctor accepts/edits them.
- Raw audio is not persisted by default.
- Published template versions and finalized documents remain immutable.
- real AI mode is visually labeled.
- Cross-tenant and cross-branch access remains fail-closed.

## Review Focus

- Microphone permission denial must not break manual visit workflow.
- Repeated audio chunks must not duplicate transcript turns.
- AI must never silently write final clinical facts.
- Active visits stay pinned to the template version selected at start.
- Corrupt/missing final artifacts must fail rather than regenerate silently.

---

### Task 1: Visit session backend

**Files:**
- Modify: `app/models.py`
- Create: `app/visit_sessions.py`
- Modify: `app/main.py`
- Test: `tests/test_visit_sessions.py`

**Interfaces:**
- Produces `POST /v1/doctor/visit-sessions`
- Produces `POST /v1/doctor/visit-sessions/{id}/audio`
- Produces `POST /v1/doctor/visit-sessions/{id}/finish`
- Produces `GET /v1/doctor/visit-sessions/{id}`

- [ ] Write failing tests for session creation, transcript order, duplicate chunk idempotency, and tenant isolation.
- [ ] Run `PYTHONPATH=. pytest -q tests/test_visit_sessions.py` and confirm RED.
- [ ] Add `ai_visit_sessions`, `ai_transcript_turns`, and `ai_field_suggestions` models.
- [ ] Add domain functions to append turns and replace suggestions.
- [ ] Register API routes.
- [ ] Run targeted tests and full backend suite.
- [ ] Commit `feat: add AI visit sessions`.

### Task 2: real AI adapter and suggestion extraction

**Files:**
- Create: `app/ai_visit.py`
- Modify: `app/main.py`
- Test: `tests/test_ai_visit.py`

**Interfaces:**
- Produces `process_audio_chunk(audio, template_fields, mode) -> VisitAiResult`
- Produces deterministic real transcript with `doctor` / `patient` roles.

- [ ] Write failing tests proving Real mode creates speaker turns and only suggests declared template fields.
- [ ] Verify RED.
- [ ] Implement real provider adapter and provider interface.
- [ ] Ensure missing facts stay absent and every suggestion carries evidence/confidence.
- [ ] Verify targeted and full backend suite.
- [ ] Commit `feat: add real AI visit extraction`.

### Task 3: Frontend foundation and routing

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/api.ts`
- Create: `web/src/styles.css`
- Test: `web/src/App.test.tsx`

**Interfaces:**
- Produces routes `/settings/templates` and `/doctor`.
- Produces API client that always injects local real-data run context headers.

- [ ] Write failing route smoke tests.
- [ ] Verify RED with `npm test`.
- [ ] Add React/Vite app shell and navigation.
- [ ] Add local API client and visible `real AI` badge.
- [ ] Verify tests and `npm run build`.
- [ ] Commit `feat: add local MIS document UI shell`.

### Task 4: Settings/Templates screen

**Files:**
- Create: `web/src/pages/TemplatesPage.tsx`
- Create: `web/src/components/TemplateUploadForm.tsx`
- Modify: `app/main.py`
- Test: `web/src/pages/TemplatesPage.test.tsx`
- Test: `tests/test_template_admin_api.py`

**Interfaces:**
- Lists templates and published versions.
- Uploads DOCX plus field/assignment metadata.
- Creates new template version and publishes/disables it.

- [ ] Write failing UI/API tests for upload, persistence after reload, new version, publish, disable.
- [ ] Verify RED.
- [ ] Add missing admin list/detail endpoints.
- [ ] Implement template list/upload/version UI.
- [ ] Verify backend tests, frontend tests, frontend build.
- [ ] Commit `feat: add template settings workspace`.

### Task 5: Doctor Cabinet and microphone flow

**Files:**
- Create: `web/src/pages/DoctorPage.tsx`
- Create: `web/src/components/VisitRecorder.tsx`
- Create: `web/src/components/TranscriptPanel.tsx`
- Create: `web/src/components/ClinicalForm.tsx`
- Test: `web/src/pages/DoctorPage.test.tsx`

**Interfaces:**
- Selects real patient context and eligible template.
- Starts a medical document and visit session.
- Uses MediaRecorder when available.
- Sends audio chunks with an idempotency key.
- Shows doctor/patient transcript and AI suggestions.
- Supports manual form entry if microphone fails.

- [ ] Write failing tests for start visit, microphone denied fallback, transcript rendering, suggestion acceptance.
- [ ] Verify RED.
- [ ] Implement Doctor Cabinet workflow.
- [ ] Keep suggestions separate from saved field values until Accept/Edit.
- [ ] Verify tests and build.
- [ ] Commit `feat: add doctor AI visit workspace`.

### Task 6: ICD-10, protocols, finalization and print

**Files:**
- Modify: `web/src/pages/DoctorPage.tsx`
- Create: `web/src/components/DiagnosisProtocolPanel.tsx`
- Create: `web/src/components/FinalDocumentPanel.tsx`
- Test: `web/src/pages/DoctorPage.test.tsx`

**Interfaces:**
- Searches ICD-10.
- Shows matching published protocols.
- Applies only doctor-selected protocol items.
- Finalizes document and exposes PDF/DOCX/Print/verification link.

- [ ] Write failing tests for ICD selection, protocol confirmation, finalize/download actions.
- [ ] Verify RED.
- [ ] Implement panels and API wiring.
- [ ] Verify frontend tests/build and backend suite.
- [ ] Commit `feat: complete doctor document workflow`.

### Task 7: Docker Compose local stack

**Files:**
- Create: `docker-compose.yml`
- Create: `web/Dockerfile`
- Create: `web/nginx.conf`
- Modify: `Dockerfile`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- `docker compose up --build`
- UI: `http://localhost:5173`
- API: `http://localhost:8080`

- [ ] Add compose config with `web`, `api`, `postgres`, persistent DB and document-storage volumes.
- [ ] Add API healthcheck and frontend reverse/static serving.
- [ ] Add CI frontend install/test/build plus backend suite.
- [ ] Document exact local commands and demo flow.
- [ ] Run CI on the branch and confirm success.
- [ ] Commit `chore: add one-command local real-data run stack`.

### Task 8: End-to-end verification

**Files:**
- Create: `docs/local-demo-checklist.md`

- [ ] Verify clean local sequence: clone → checkout branch → `docker compose up --build`.
- [ ] Verify Settings/Templates upload/publish flow.
- [ ] Verify Doctor Cabinet start visit → real transcript → suggestions → accept/edit.
- [ ] Verify ICD/protocol selection.
- [ ] Verify PDF/DOCX download and print.
- [ ] Verify QR opens the same immutable PDF.
- [ ] Verify page reload preserves template and finalized document state.
- [ ] Record exact verification steps in `docs/local-demo-checklist.md`.
- [ ] Commit `test: document local end-to-end demo verification`.


## Real-data integration amendment

- Do not create seeded patients, fake practitioners, deterministic transcripts, or fake clinical suggestions.
- Add a MIS upstream adapter that calls:
  - `GET /api/products/mis/v1/patients?branch_id=<uuid>`
  - `GET /api/products/mis/v1/practitioners?branch_id=<uuid>`
  - `GET /api/products/mis/v1/patients/:patientId`
- Forward `Authorization: Bearer ...` from configured backend credentials or incoming authorized session.
- The speech pipeline must return real `doctor` / `patient` speaker turns.
- The extraction pipeline must return structured field suggestions from a configured real LLM endpoint.
- Misconfigured providers must return explicit 503/configuration errors; no fake fallback.
