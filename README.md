# IMDS Medical Document Service

Standalone MIS module for reusable medical DOCX templates.

## Implemented

- Admin uploads a DOCX template once; it persists until disabled. Changes create a new immutable version while existing patient documents retain their original template version.
- Templates can be assigned by specialty, practitioner, branch and visit type.
- Doctors see eligible published templates and create patient-specific drafts.
- Declared text fields support field-scoped speech-to-text; transcript returns as a draft and is not auto-saved.
- ICD-10 catalog import/search is supported from an authorized CSV with `code,title`.
- Versioned clinical protocols can be mapped to ICD-10 codes and contain selectable treatment/investigation items.
- Finalization replaces declared placeholders, appends a signed QR, converts DOCX to PDF locally with LibreOffice, stores immutable DOCX/PDF and SHA-256.
- Re-finalization reuses the exact stored artifact.
- QR contains no PHI; it carries a signed opaque reference to the finalized document.
- Cross-tenant document access fails closed at the API query layer.

## Template placeholders

```text
{{patient.full_name}}
{{complaints}}
{{diagnosis_text}}
```

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export QR_SIGNING_SECRET='replace-with-a-long-random-secret'
uvicorn app.server:app --host 0.0.0.0 --port 8080
```

LibreOffice must be installed for PDF generation.

## Trusted MIS context

Current integration expects these headers from the IMDS API gateway:

- `X-Tenant-ID`
- `X-User-ID`
- `X-Branch-ID`
- `X-Practitioner-ID`
- `X-Specialty-Code`

Do not expose the service directly with client-controlled headers. The gateway must derive them from authenticated platform context.

## Speech-to-text

Set `STT_URL` to a self-hosted service. Raw audio is POSTed with its original content type. Expected response:

```json
{"text":"recognized text"}
```

Audio is not persisted by this module.

## ICD-10

The repository intentionally does not bundle an ICD-10 dataset. Import a dataset your organization is authorized to use.

## Clinical safety

Protocol selection does not automatically prescribe treatment. The doctor workflow must require practitioner confirmation before protocol items become orders/plan items.
