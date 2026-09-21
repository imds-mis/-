# IMDS Medical Documents

Portable MIS medical-document module with:

- **Settings → Templates** — persistent DOCX templates, versions, assignments and publishing.
- **Doctor Cabinet** — real MIS patient selection, template selection, microphone capture, doctor/patient transcript, AI field suggestions, ICD-10, clinical protocols, PDF/DOCX and QR verification.
- PostgreSQL persistence.
- Local LibreOffice rendering.
- No Cloudflare.
- No Supabase.
- No demo patients or fabricated transcript mode.

## Local start

Clone and open the feature branch:

```bash
git clone https://github.com/imds-mis/-.git
cd -
git checkout feat/medical-document-service
cp .env.example .env
```

Fill the real integration values in `.env`:

```env
MIS_UPSTREAM_URL=https://mis.imds.kz
MIS_AUTH_TOKEN=<real MIS bearer token>

SPEECH_PIPELINE_URL=http://host.docker.internal:9000

LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=<real provider key>
LLM_MODEL=<model name>

QR_SIGNING_SECRET=<long random secret>
```

Then run:

```bash
docker compose up --build
```

Open:

- **Doctor Cabinet:** http://localhost:5173/doctor
- **Settings → Templates:** http://localhost:5173/settings/templates
- **API health:** http://localhost:8080/healthz

The browser UI asks for the real MIS context values:

- Tenant UUID
- User UUID
- Branch UUID
- Practitioner UUID
- Specialty code

These are used only against the local service. The upstream bearer token stays on the backend in `.env` and is never sent to the browser.

## Real MIS data

The backend proxies the existing MIS endpoints:

```text
GET /api/products/mis/v1/patients
GET /api/products/mis/v1/patients/:patientId
GET /api/products/mis/v1/practitioners
```

The local browser uses:

```text
GET /v1/integrations/mis/patients
GET /v1/integrations/mis/patients/:patientId
GET /v1/integrations/mis/practitioners
```

No local patient seeds are created.

## Real speech + speaker separation contract

`SPEECH_PIPELINE_URL` must point to a real service that accepts audio and returns speaker-separated turns.

Chunk request:

```http
POST {SPEECH_PIPELINE_URL}/transcribe
Content-Type: audio/webm
X-Session-ID: <uuid>
X-Chunk-ID: <unique chunk id>
```

Response:

```json
{
  "turns": [
    {
      "speaker": "doctor",
      "text": "Что вас беспокоит?",
      "confidence": 0.97,
      "started_ms": 0,
      "ended_ms": 1600
    },
    {
      "speaker": "patient",
      "text": "Боль внизу живота второй день.",
      "confidence": 0.94,
      "started_ms": 1700,
      "ended_ms": 4400
    }
  ]
}
```

When the conversation finishes:

```http
POST {SPEECH_PIPELINE_URL}/finalize
X-Session-ID: <uuid>
```

The final response uses the same `turns` structure. The service rejects speaker labels other than `doctor` or `patient` so an unclassified speaker cannot silently become a clinical role.

Raw audio is not persisted by this module.

## Real clinical extraction

`LLM_BASE_URL` is an OpenAI-compatible API base ending before `/chat/completions`, for example:

```text
http://host.docker.internal:11434/v1
```

The extraction engine receives:

- declared template fields;
- real transcript turns;
- patient/system context.

It may return only suggestions for declared fields. Unsupported fields and unsupported evidence indexes are rejected. AI suggestions remain drafts until the doctor explicitly accepts or edits them.

## Template workflow

1. Open **Settings → Templates**.
2. Upload a DOCX.
3. Define structured fields.
4. Publish the template.
5. The template remains until disabled.
6. A changed template is added as a new version.
7. Old patient documents stay pinned to their original template version.

Example placeholders:

```text
{{patient.full_name}}
{{complaints}}
{{anamnesis_morbi}}
{{objective_status}}
{{diagnosis_text}}
{{recommendations}}
```

## Doctor workflow

1. Open **Doctor Cabinet**.
2. Enter the real tenant/user/branch/practitioner/specialty context.
3. Select a real patient from MIS.
4. Select an eligible published examination template.
5. Click **Начать прием и включить микрофон**.
6. The browser sends real microphone chunks to the configured speech service.
7. Transcript appears as **Врач / Пациент**.
8. AI creates field-scoped draft suggestions.
9. Doctor accepts, edits or ignores them.
10. Doctor searches ICD-10 and selects the canonical code.
11. Matching published clinical protocols are shown.
12. Doctor completes missing fields.
13. Finalization freezes immutable DOCX/PDF, SHA-256 and QR verification.

## ICD-10

The repository intentionally does not bundle an ICD-10 dataset. Import only a dataset your organization is authorized to use.

## Security note

The local context fields are acceptable for isolated development only. In production, tenant/user/branch/practitioner context must come from authenticated platform-core/gateway context and not from user-controlled browser headers.
