# Local real-data verification checklist

## Preconditions

- Docker Desktop / Docker Engine running.
- Real MIS bearer token available.
- Real tenant/user/branch/practitioner IDs available.
- Real speech pipeline reachable from Docker.
- Real OpenAI-compatible clinical extraction endpoint reachable from Docker.

## Start

```bash
git clone https://github.com/imds-mis/-.git imds-medical-documents
cd imds-medical-documents
git checkout feat/medical-document-service
cp .env.example .env
# edit .env with real credentials/endpoints
docker compose up --build
```

Expected:

- http://localhost:5173/doctor opens.
- http://localhost:5173/settings/templates opens.
- http://localhost:8080/healthz returns HTTP 200.

## Settings → Templates

1. Enter real tenant/user/branch/practitioner IDs.
2. Upload a DOCX with declared placeholders.
3. Verify it appears in the template list.
4. Publish it.
5. Reload page.
6. Verify template persists and remains published.

## Doctor Cabinet

1. Enter the same real MIS context.
2. Verify the patient selector loads real patients from upstream MIS.
3. Select the published template.
4. Click **Начать прием и включить микрофон**.
5. Grant microphone permission.
6. Speak as doctor and patient.
7. Verify transcript displays separate Doctor/Patient turns from the real speech pipeline.
8. Verify AI suggestions appear but are not automatically saved.
9. Accept one suggestion and manually edit another.
10. Search/select an ICD-10 code.
11. Inspect matching clinical protocol.
12. Finish and generate document.
13. Download PDF.
14. Download DOCX.
15. Open print flow.
16. Open QR verification link and confirm it returns the same finalized PDF.

## Persistence

1. Stop stack with `docker compose down`.
2. Start again with `docker compose up`.
3. Verify PostgreSQL data and document files are still present.

## Negative checks

- Remove `MIS_AUTH_TOKEN`: patient list must fail explicitly; no fake patients.
- Remove `SPEECH_PIPELINE_URL`: visit session must return configuration error; no fake transcript.
- Remove LLM configuration: visit session must return configuration error; no fake field suggestions.
- Use another tenant/branch header for an existing document: access must be denied/not found.
