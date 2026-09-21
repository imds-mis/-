# Medical Document Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, testable MIS medical document service in `imds-mis/-` that persists reusable DOCX templates, exposes specialty-scoped doctor forms, supports ICD-10/protocol selection and field-scoped speech-to-text, and finalizes immutable downloadable documents with signed QR verification.

**Architecture:** Fastify + TypeScript API with PostgreSQL as system of record and a filesystem object-store adapter. Medical templates and protocol versions are immutable once published. Rendering is isolated behind adapters so the API can run/test without LibreOffice while production can render DOCX/PDF locally.

**Tech Stack:** Node.js 24, TypeScript, Fastify, PostgreSQL, Zod, @fastify/multipart, docxtemplater/pizzip, qrcode, pdf-lib, Node test runner.

**Spec:** `docs/specs/2026-09-21-medical-document-service.md`

## Global Constraints

- No Cloudflare.
- No Supabase.
- Tenant and branch isolation is mandatory.
- Published template/protocol versions are immutable.
- Finalized document artifacts are immutable.
- QR contains no PHI.
- Dictation is scoped to one selected field and requires practitioner acceptance.
- ICD-10/protocol selection remains practitioner-confirmed.

## Review Focus

- Cross-tenant or cross-branch access must fail closed.
- Published template versions must never be mutated in place.
- Dictation must not write into a different field than the requested field id.
- Finalization must be idempotent and must not regenerate a different artifact on later downloads.
- QR verification must reject tampered or revoked tokens.

---

### Task 1: Service scaffold and health API

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `src/app.ts`
- Create: `src/server.ts`
- Test: `test/app.test.ts`

**Interfaces:**
- Produces: `buildApp(deps): FastifyInstance`

- [ ] Write failing health-route test.
- [ ] Run test and verify route is missing.
- [ ] Implement service scaffold and health route.
- [ ] Run tests and typecheck.
- [ ] Commit.

### Task 2: Persistence model, tenancy, templates and assignments

**Files:**
- Create: `db/migrations/001_init.sql`
- Create: `src/context.ts`
- Create: `src/templates.ts`
- Test: `test/template-domain.test.ts`

**Interfaces:**
- Produces template lifecycle and eligibility query contract consumed by document routes.

- [ ] Test versioning/eligibility rules first.
- [ ] Add PostgreSQL schema with tenant_id/branch_id and RLS-ready indexes.
- [ ] Implement template upload metadata, version publish/disable and assignments.
- [ ] Verify tests/typecheck.
- [ ] Commit.

### Task 3: ICD-10 and clinical protocol catalogs

**Files:**
- Create: `src/catalogs.ts`
- Test: `test/catalog-domain.test.ts`

**Interfaces:**
- Produces search/import contracts and immutable protocol-version model.

- [ ] Test normalized ICD search and protocol-to-ICD mappings first.
- [ ] Implement CSV import parser/search helpers and protocol routes.
- [ ] Verify tests/typecheck.
- [ ] Commit.

### Task 4: Patient document instances and field-level dictation

**Files:**
- Create: `src/documents.ts`
- Create: `src/speech.ts`
- Test: `test/document-domain.test.ts`
- Test: `test/speech.test.ts`

**Interfaces:**
- Produces document draft/update API and `transcribeField(fieldId,...)` contract.

- [ ] Test doctor eligibility and immutable template snapshot behavior.
- [ ] Test that STT response is bound to exactly one field id and unsupported field types are rejected.
- [ ] Implement document draft/update routes.
- [ ] Implement configurable self-hosted STT adapter and draft transcription response.
- [ ] Verify tests/typecheck.
- [ ] Commit.

### Task 5: Rendering, immutable artifact storage and signed QR

**Files:**
- Create: `src/storage.ts`
- Create: `src/rendering.ts`
- Create: `src/qr.ts`
- Test: `test/qr.test.ts`
- Test: `test/finalization.test.ts`

**Interfaces:**
- Produces finalization function returning stored PDF/DOCX metadata and public verification token.

- [ ] Test QR tamper rejection and token hashing first.
- [ ] Test finalization idempotency first.
- [ ] Implement local filesystem object store.
- [ ] Implement DOCX placeholder render adapter, LibreOffice PDF adapter and QR overlay.
- [ ] Persist hash after QR insertion and reuse immutable artifact on downloads.
- [ ] Verify tests/typecheck.
- [ ] Commit.

### Task 6: API composition, CI and operator documentation

**Files:**
- Modify: `src/app.ts`
- Create: `.github/workflows/ci.yml`
- Create: `.env.example`
- Create: `README.md`
- Create: `docs/api.md`

**Interfaces:**
- Consumes all route registrars and runtime adapters.

- [ ] Add route-registration smoke test first.
- [ ] Register admin/doctor/public APIs.
- [ ] Add CI for install, typecheck and tests.
- [ ] Document local run, PostgreSQL migration, storage, LibreOffice and STT endpoint contract.
- [ ] Run full suite/typecheck.
- [ ] Commit.
