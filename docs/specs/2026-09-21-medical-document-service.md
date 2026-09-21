# MIS Medical Document Service Specification

**Date:** 2026-09-21

## Goal

Build a standalone MIS module for reusable medical document templates. An administrator uploads a DOCX template once; it remains active until a new version is published or it is disabled. Doctors see only templates assigned to their specialty/profile, fill a patient-specific instance, may dictate selected text fields with speech-to-text, select ICD-10 diagnoses and approved treatment protocols, then finalize and download an immutable document with a secure QR code that reopens the exact finalized version.

## Core workflow

1. Administrator uploads a DOCX template.
2. The service stores the original file and creates immutable template version 1.
3. Administrator defines fields and assigns the template to specialties, optional doctors, branches and visit types.
4. Publishing makes that version available to eligible doctors.
5. Doctor selects the template in the patient encounter.
6. Patient/doctor/clinic metadata is auto-filled; doctor fills clinical fields.
7. Text-capable fields can accept field-scoped speech-to-text. Transcription is a draft and requires the doctor to accept or edit it.
8. Doctor may search/select ICD-10 codes and related approved clinical protocol versions.
9. Doctor finalizes the document.
10. Service renders DOCX, converts it to PDF, calculates SHA-256, overlays a secure QR, stores the immutable final artifact and its hash.
11. Download always returns the stored immutable artifact rather than re-rendering from a newer template.
12. Scanning the QR opens the same finalized document through a signed opaque token.

## Template rules

- Supported upload: DOCX.
- A template is persistent until explicitly disabled.
- Editing a published template creates a new version; existing finalized documents never change.
- Template fields support: text, textarea, number, date, datetime, boolean, select, multiselect, ICD-10 diagnosis, protocol selector and read-only system variables.
- System variables include patient, encounter, practitioner, tenant/clinic and branch values.
- Template assignment can target specialties, explicit practitioners, branches and visit types.
- A doctor cannot modify template layout/version metadata.

## Document lifecycle

- draft
- completed
- finalized
- revoked

Finalized documents are immutable. Corrections create a new document version linked to the prior one.

## QR security

The QR contains no PHI. It contains an opaque, high-entropy signed token referencing a finalized document version.

- HMAC-SHA256 signed token.
- Signing key stored only as runtime secret.
- Token payload contains document public id, version id, issued-at and nonce.
- Database stores token hash, not the raw token.
- Public viewer validates signature and token hash before serving the artifact.
- QR access mode is configurable: signed-link or authenticated.
- Audit events include QR scans and downloads.

## Storage

- Local filesystem storage adapter in development and production-compatible persistent mounted volume.
- No Cloudflare or Supabase dependency.
- Stored objects: source template DOCX, rendered DOCX, final PDF, optional attachments.
- Final PDF/DOCX objects are immutable after finalization.

## ICD-10

- Catalog table supports code, title, locale, version/source metadata and active status.
- Search by code and normalized title.
- Bulk CSV import for an authorized/official ICD-10 dataset.
- The application must not silently invent codes.
- Doctor explicitly confirms the selected diagnosis.

## Clinical protocols

- Versioned catalog with title, source organization, approval/effective dates, status, source URL/document and ICD-10 mappings.
- Protocol versions are immutable once published.
- Structured protocol items may include investigation, medication, procedure, recommendation, follow-up and other.
- Selecting a protocol never auto-orders treatment. Doctor explicitly selects/accepts items before they are copied into the patient treatment plan/document.
- Patient document stores protocol version snapshot/reference.

## Speech-to-text

- Dictation is scoped to exactly one active field.
- Only text/textarea fields support free dictation.
- ICD-10/protocol fields use recognized speech only as search text; doctor must select a canonical record.
- Browser records audio; API sends it to a configurable self-hosted STT endpoint.
- No external cloud STT is required.
- Transcription response is a draft; UI provides Accept / Replace / Cancel.
- Audio is not retained by default after transcription.

## Multi-tenant and branch isolation

Every tenant-owned table contains tenant_id. Patient documents also contain branch_id. Database row-level security and API context must prevent cross-tenant and unauthorized cross-branch access.

## Audit

Audit at minimum:
- template.uploaded
- template.version.created
- template.published
- template.disabled
- document.created
- document.updated
- document.finalized
- document.downloaded
- document.revoked
- diagnosis.selected
- protocol.selected
- speech.transcribed
- qr.scanned

## API surfaces

Admin:
- template upload/list/version/publish/disable
- template field configuration
- template assignment
- ICD import/search
- protocol create/version/publish/map ICD

Doctor:
- eligible templates
- create patient document
- update field values
- speech transcription
- ICD search/select
- protocol search/select/apply selected items
- finalize
- download PDF/DOCX
- list patient/doctor documents

Public:
- QR verification/viewer using signed token

## Rendering

DOCX rendering replaces declared placeholders using structured field/system values. Final PDF is produced via a local headless LibreOffice process, then QR is overlaid into the final PDF. Final artifact hash is calculated after QR insertion and stored with the artifact.

## Non-goals for first release

- Editing arbitrary Word layout in-browser.
- Automatic medical diagnosis.
- Automatic treatment prescription without practitioner confirmation.
- External public cloud storage or authentication.
