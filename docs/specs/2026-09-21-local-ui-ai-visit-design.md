# MIS Local UI + AI Visit Capture Design

**Date:** 2026-09-21  
**Repository:** `imds-mis/-`  
**Branch:** `feat/medical-document-service`

## 1. Outcome

Add a local browser UI on top of the existing Medical Document Service with two primary workspaces:

1. **Settings → Templates** for administrators.
2. **Doctor Cabinet** for clinical use.

The local environment must start with Docker Compose and allow an end-to-end real-data workflow:

```text
Admin uploads DOCX once
→ publishes template and assigns specialty
→ doctor opens cabinet
→ chooses patient + template
→ Start visit
→ microphone records conversation
→ AI returns speaker-separated transcript (doctor / patient)
→ AI creates draft values for template fields
→ doctor reviews/edits
→ doctor selects ICD-10 + clinical protocol
→ Finalize
→ PDF/DOCX + QR
→ Print / Download
```

Existing backend guarantees remain authoritative: template versioning, tenant/branch isolation, immutable finalized artifacts, signed QR, ICD-10 catalog, and protocol catalog.

## 2. Local stack

### Frontend

- React
- Vite
- TypeScript
- Browser MediaRecorder API
- No third-party cloud UI runtime

### Backend

Existing FastAPI service, extended with AI visit capture endpoints.

### Persistence

- PostgreSQL in Docker Compose for normal local demo
- Persistent Docker volume for generated DOCX/PDF/template files

### Document rendering

- LibreOffice inside the API container

### AI adapters

The backend uses real provider-neutral integrations only:

- real MIS upstream for patients/practitioners
- real speech + speaker-separation pipeline via `SPEECH_PIPELINE_URL`
- real OpenAI-compatible clinical extraction via `LLM_BASE_URL`

If any required provider is not configured, the affected workflow fails explicitly with a configuration error. No synthetic patients, fake transcript, or demo AI response is generated.

No Cloudflare and no Supabase.

## 3. Screen A — Settings → Templates

Route:

```text
/settings/templates
```

Layout:

### Template list

Each row/card shows:

- template name
- specialty
- current published version
- active / disabled
- updated date
- actions

Actions:

- Open
- New version
- Disable
- Preview fields

### Upload form

Admin provides:

- DOCX file
- name
- specialty
- optional branch
- optional practitioner
- optional visit type
- field definition JSON/UI mapping

Primary action:

```text
Upload template
```

A new template starts at `v1`.

### Version behavior

If an existing template is changed:

```text
v1 published
→ New version
→ v2 draft
→ Publish
→ v2 becomes current
```

Old patient documents remain pinned to their original template version.

## 4. Screen B — Doctor Cabinet

Route:

```text
/doctor
```

Main sections:

### Patient context

Patient context is loaded from the configured real MIS upstream API using the authenticated upstream bearer token and branch scope.

The local UI does not create fake patients.

### Template selector

Only published templates eligible for the doctor's:

- tenant
- branch
- specialty
- practitioner
- visit type

are shown.

### Start Visit

Primary button:

```text
Start visit
```

After clicking:

- create a patient document draft
- create an AI visit session
- request microphone permission
- start MediaRecorder
- stream/send short audio chunks to the backend
- show recording state and timer

Buttons while active:

- Pause
- Resume
- Finish conversation

## 5. AI visit capture

### Audio handling

Browser records microphone audio in chunks.

Audio is sent to:

```text
POST /v1/doctor/visit-sessions/{session_id}/audio
```

Audio is ephemeral by default.

Raw audio is deleted after transcription unless explicit retention is enabled by clinic policy.

### Speaker separation

The AI layer returns speaker turns:

```json
[
  {
    "speaker": "doctor",
    "text": "Что вас беспокоит?"
  },
  {
    "speaker": "patient",
    "text": "Боль внизу живота около двух дней."
  }
]
```

The system distinguishes conversational role, not legal identity.

Speaker-role classification is a draft inference and remains reviewable.

### Transcript UI

The Doctor Cabinet displays:

```text
Doctor  14:21
Что вас беспокоит?

Patient 14:21
Боль внизу живота около двух дней.
```

Color/style may differentiate speakers, but the data model uses neutral `doctor` / `patient` labels.

## 6. Automatic template filling

Every template field can declare an AI extraction hint.

Example:

```json
{
  "id": "complaints",
  "type": "textarea",
  "label": "Жалобы",
  "ai_hint": "Patient complaints, symptoms, duration and location",
  "ai_source": "patient"
}
```

Supported sources:

- patient
- doctor
- both
- system

After transcript updates, the backend produces **draft suggestions**, not final chart data.

Example:

```json
{
  "complaints": {
    "value": "Боль внизу живота в течение двух дней",
    "confidence": 0.92,
    "evidence_turn_ids": ["turn-12"],
    "status": "suggested"
  }
}
```

### Important safety behavior

AI suggestions never automatically finalize medical documentation.

The doctor must review and explicitly accept/edit before finalization.

Fields with low confidence are highlighted.

Unsupported or absent facts remain empty; the system must not invent them.

## 7. Doctor review phase

After `Finish conversation`:

UI switches to Review mode.

Left side:

- transcript

Right side:

- template fields

Each field shows:

- label
- AI suggestion
- confidence indicator
- source speaker
- Accept / Edit / Clear

Doctor can type missing information manually.

A microphone button remains available for manual dictation into a selected text field.

## 8. ICD-10

The review screen contains:

```text
Diagnosis
[ Search ICD-10... ]
```

Search is by:

- code
- title

Selected code is canonical catalog data.

Speech or AI can propose a search query, but cannot silently set a canonical diagnosis.

The doctor explicitly selects/accepts the ICD-10 record.

## 9. Clinical protocol

After ICD-10 selection, the UI shows matching published protocol versions.

Example:

```text
N80 — Endometriosis

Clinical protocols
[ Endometriosis protocol v1 ]
```

Opening a protocol shows structured items:

- investigations
- medications
- procedures
- recommendations
- follow-up

The doctor selects applicable items.

No treatment item becomes an order automatically.

## 10. Finalization

Doctor presses:

```text
Finalize visit
```

Backend:

1. validates required fields
2. stores accepted field values
3. pins the exact template version
4. renders DOCX
5. embeds verification QR
6. converts DOCX to PDF
7. computes SHA-256
8. freezes artifacts
9. stores QR token hash
10. marks document finalized

UI then displays:

- View PDF
- Download PDF
- Download DOCX
- Print
- Copy verification link

## 11. Local navigation

Top navigation:

```text
IMDS Medical Documents

Doctor Cabinet | Settings / Templates
```

Local access still uses explicit role routes, but patient/practitioner data and clinical context come from the real MIS API.

## 12. Visit session data model

Add:

### ai_visit_sessions

- id
- tenant_id
- branch_id
- patient_id
- practitioner_id
- document_id
- status: idle / recording / processing / review / completed / failed
- started_at
- ended_at
- created_at

### ai_transcript_turns

- id
- session_id
- sequence_no
- speaker
- text
- confidence
- started_ms
- ended_ms

### ai_field_suggestions

- id
- session_id
- field_id
- value_json
- confidence
- evidence_turn_ids
- status: suggested / accepted / rejected / edited

Audio bytes are not stored in these tables.

## 13. API extensions

### Sessions

```text
POST /v1/doctor/visit-sessions
GET  /v1/doctor/visit-sessions/{id}
POST /v1/doctor/visit-sessions/{id}/audio
POST /v1/doctor/visit-sessions/{id}/finish
```

### Suggestions

```text
GET  /v1/doctor/visit-sessions/{id}/suggestions
POST /v1/doctor/visit-sessions/{id}/suggestions/{field_id}/accept
POST /v1/doctor/visit-sessions/{id}/suggestions/{field_id}/reject
```

### Transcript

```text
GET /v1/doctor/visit-sessions/{id}/transcript
```

Existing template, ICD, protocol, field update, finalization and download endpoints are reused.

## 14. Provider contracts

### Speech / diarization adapter

Input:

- audio bytes
- mime type
- locale
- session id

Output:

- ordered speaker turns
- confidence

### Clinical extraction adapter

Input:

- template field definitions
- current transcript
- existing system values

Output:

- field-scoped draft suggestions with evidence

No adapter can finalize a document.

## 15. Real AI runtime

Required runtime integrations:

- `MIS_UPSTREAM_URL` — real MIS API base URL.
- `MIS_AUTH_TOKEN` — bearer token used by the local backend to call the real MIS API.
- `SPEECH_PIPELINE_URL` — real STT + speaker diarization endpoint.
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` — real clinical extraction endpoint.

If one of these required integrations is unavailable, the corresponding workflow returns an explicit configuration error. The system must not synthesize fake clinical content.

## 16. Docker Compose

```text
docker compose up --build
```

Services:

- `web` — React/Vite production build served locally
- `api` — FastAPI + LibreOffice
- `postgres` — PostgreSQL

Ports:

- UI: `http://localhost:5173`
- API: `http://localhost:8080`

Persistent volumes:

- PostgreSQL
- medical document storage

## 17. Acceptance criteria

The local build is accepted when all of the following work from a clean checkout:

1. `docker compose up --build` starts the stack.
2. Browser opens Settings/Templates.
3. Admin uploads a DOCX template and publishes it.
4. The template remains available after page reload.
5. Doctor Cabinet shows the template for the configured specialty.
6. Doctor starts a visit and grants microphone permission.
7. Transcript UI shows doctor/patient turns from the real speech/diarization pipeline.
8. Template fields receive AI draft suggestions.
9. Doctor can accept/edit suggestions.
10. Doctor can search and select ICD-10.
11. Matching clinical protocol can be selected.
12. Finalize creates immutable DOCX/PDF.
13. PDF/DOCX can be downloaded.
14. Print action opens browser print flow for PDF.
15. QR opens the same finalized PDF.
16. Cross-tenant document access remains blocked.
17. CI covers backend domain/API behavior and frontend build/tests.

## 18. Deferred from this increment

- production SSO wiring to the main IMDS platform
- production patient directory integration
- permanent audio recording/archive
- voice biometric identity verification
- automatic treatment ordering
- arbitrary WYSIWYG Word editor
- deployment to production infrastructure

These are intentionally excluded from this local real-data implementation.
