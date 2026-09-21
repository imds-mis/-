export type LocalContext = {
  tenantId: string;
  userId: string;
  branchId: string;
  practitionerId: string;
  specialtyCode: string;
};

export type Practitioner = {
  id: string;
  practitioner_number?: string | null;
  first_name: string;
  last_name: string;
  middle_name?: string | null;
};

export type Patient = {
  id: string;
  medical_record_number?: string | null;
  first_name: string;
  last_name: string;
  middle_name?: string | null;
  date_of_birth?: string | null;
};

export type TemplateField = {
  id: string;
  label?: string;
  type: string;
  ai_hint?: string;
  ai_source?: "patient" | "doctor" | "both" | "system";
  required?: boolean;
};

export type TemplateSummary = {
  id: string;
  name: string;
  active: boolean;
  versions: Array<{ id: string; version: number; status: string; fields: TemplateField[] }>;
  assignments: Array<{
    specialty_code?: string | null;
    branch_id?: string | null;
    practitioner_id?: string | null;
    visit_type?: string | null;
  }>;
};

export type TranscriptTurn = {
  id: string;
  sequence_no: number;
  speaker: "doctor" | "patient";
  text: string;
  confidence?: number | null;
};

export type FieldSuggestion = {
  id: string;
  field_id: string;
  value: unknown;
  confidence?: number | null;
  evidence_turn_ids: string[];
  status: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";

export function defaultContext(): LocalContext {
  return {
    tenantId: import.meta.env.VITE_TENANT_ID || "local-tenant",
    userId: import.meta.env.VITE_USER_ID || "local-user",
    branchId: import.meta.env.VITE_BRANCH_ID || "local-branch",
    practitionerId: import.meta.env.VITE_PRACTITIONER_ID || "local-doctor-1",
    specialtyCode: import.meta.env.VITE_SPECIALTY_CODE || "GYNE",
  };
}

export function saveContext(_context: LocalContext): void {
  // Local mode intentionally has no editable technical context UI.
}

function requestHeaders(context: LocalContext, json = true): HeadersInit {
  const value: Record<string, string> = {
    "X-Tenant-ID": context.tenantId,
    "X-User-ID": context.userId,
    "X-Branch-ID": context.branchId,
    "X-Practitioner-ID": context.practitionerId,
    "X-Specialty-Code": context.specialtyCode,
  };
  if (json) value["Content-Type"] = "application/json";
  return value;
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.error || ("HTTP " + response.status));
  }
  return response.json() as Promise<T>;
}

export async function getPractitioners(context: LocalContext): Promise<Practitioner[]> {
  const response = await fetch(API_BASE + "/v1/integrations/mis/practitioners", { headers: requestHeaders(context, false) });
  return (await parse<{ data: Practitioner[] }>(response)).data;
}

export async function getPatients(context: LocalContext): Promise<Patient[]> {
  const response = await fetch(API_BASE + "/v1/integrations/mis/patients", { headers: requestHeaders(context, false) });
  return (await parse<{ data: Patient[] }>(response)).data;
}

export async function getTemplates(context: LocalContext): Promise<TemplateSummary[]> {
  const response = await fetch(API_BASE + "/v1/admin/templates", { headers: requestHeaders(context, false) });
  return (await parse<{ data: TemplateSummary[] }>(response)).data;
}

export async function getEligibleTemplates(context: LocalContext): Promise<Array<{id:string;name:string;version:number;fields:TemplateField[]}>> {
  const response = await fetch(API_BASE + "/v1/doctor/templates", { headers: requestHeaders(context, false) });
  return (await parse<{ data: Array<{id:string;name:string;version:number;fields:TemplateField[]}> }>(response)).data;
}

export async function inspectTemplate(context: LocalContext, file: File): Promise<TemplateField[]> {
  const form = new FormData();
  form.set("file", file);
  const response = await fetch(API_BASE + "/v1/admin/templates/inspect", {
    method: "POST",
    headers: requestHeaders(context, false),
    body: form
  });
  return (await parse<{ data: { fields: TemplateField[] } }>(response)).data.fields;
}

export async function uploadTemplate(
  context: LocalContext,
  input: { name: string; file: File; fields: TemplateField[]; specialtyCode: string; practitionerId?: string; visitType?: string }
): Promise<void> {
  const form = new FormData();
  form.set("name", input.name);
  form.set("fields_json", JSON.stringify(input.fields));
  form.set("assignments_json", JSON.stringify([{
    specialty_code: input.specialtyCode || null,
    branch_id: context.branchId || null,
    practitioner_id: input.practitionerId || null,
    visit_type: input.visitType || null,
  }]));
  form.set("file", input.file);
  const response = await fetch(API_BASE + "/v1/admin/templates", {
    method: "POST",
    headers: requestHeaders(context, false),
    body: form
  });
  await parse(response);
}


export async function createTemplateVersion(
  context: LocalContext,
  templateId: string,
  file: File,
  fields: TemplateField[]
): Promise<void> {
  const form = new FormData();
  form.set("fields_json", JSON.stringify(fields));
  form.set("file", file);
  const response = await fetch(API_BASE + "/v1/admin/templates/" + templateId + "/versions", {
    method: "POST",
    headers: requestHeaders(context, false),
    body: form
  });
  await parse(response);
}

export async function publishTemplate(context: LocalContext, templateId: string): Promise<void> {
  const response = await fetch(API_BASE + "/v1/admin/templates/" + templateId + "/publish", {
    method: "POST",
    headers: requestHeaders(context, false)
  });
  await parse(response);
}

export async function disableTemplate(context: LocalContext, templateId: string): Promise<void> {
  const response = await fetch(API_BASE + "/v1/admin/templates/" + templateId + "/disable", {
    method: "POST",
    headers: requestHeaders(context, false)
  });
  await parse(response);
}

export async function createDocument(context: LocalContext, templateId: string, patient: Patient) {
  const response = await fetch(API_BASE + "/v1/doctor/documents", {
    method: "POST",
    headers: requestHeaders(context),
    body: JSON.stringify({
      template_id: templateId,
      patient_id: patient.id,
      system_values: {
        "patient.full_name": [patient.last_name, patient.first_name, patient.middle_name].filter(Boolean).join(" "),
        "patient.medical_record_number": patient.medical_record_number || "",
        "patient.date_of_birth": patient.date_of_birth || ""
      }
    })
  });
  return (await parse<{ data: any }>(response)).data;
}

export async function createVisitSession(context: LocalContext, documentId: string, patientId: string) {
  const response = await fetch(API_BASE + "/v1/doctor/visit-sessions", {
    method: "POST",
    headers: requestHeaders(context),
    body: JSON.stringify({ document_id: documentId, patient_id: patientId })
  });
  return (await parse<{ data: any }>(response)).data;
}

export async function uploadAudioChunk(context: LocalContext, sessionId: string, chunkId: string, blob: Blob) {
  const form = new FormData();
  form.set("chunk_id", chunkId);
  form.set("audio", new File([blob], chunkId + ".webm", { type: blob.type || "audio/webm" }));
  const response = await fetch(API_BASE + "/v1/doctor/visit-sessions/" + sessionId + "/audio", {
    method: "POST",
    headers: requestHeaders(context, false),
    body: form
  });
  return (await parse<{ data: { transcript: TranscriptTurn[]; suggestions: FieldSuggestion[] } }>(response)).data;
}

export async function finishVisitSession(context: LocalContext, sessionId: string) {
  const response = await fetch(API_BASE + "/v1/doctor/visit-sessions/" + sessionId + "/finish", {
    method: "POST",
    headers: requestHeaders(context, false)
  });
  return (await parse<{ data: { transcript: TranscriptTurn[]; suggestions: FieldSuggestion[]; status: string } }>(response)).data;
}

export async function acceptSuggestion(context: LocalContext, sessionId: string, fieldId: string) {
  const response = await fetch(
    API_BASE + "/v1/doctor/visit-sessions/" + sessionId + "/suggestions/" + encodeURIComponent(fieldId) + "/accept",
    { method: "POST", headers: requestHeaders(context, false) }
  );
  return (await parse<{ data: any }>(response)).data;
}

export async function updateDocumentFields(context: LocalContext, documentId: string, values: Record<string, unknown>) {
  const response = await fetch(API_BASE + "/v1/doctor/documents/" + documentId + "/fields", {
    method: "PATCH",
    headers: requestHeaders(context),
    body: JSON.stringify({ values })
  });
  return (await parse<{ data: any }>(response)).data;
}

export async function searchIcd(context: LocalContext, q: string) {
  const response = await fetch(API_BASE + "/v1/doctor/icd10?q=" + encodeURIComponent(q), {
    headers: requestHeaders(context, false)
  });
  return (await parse<{ data: Array<{code:string;title:string;version?:string;source?:string}> }>(response)).data;
}

export async function getProtocols(context: LocalContext, icdCode: string) {
  const response = await fetch(API_BASE + "/v1/doctor/protocols?icd_code=" + encodeURIComponent(icdCode), {
    headers: requestHeaders(context, false)
  });
  return (await parse<{ data: any[] }>(response)).data;
}

export async function finalizeDocument(context: LocalContext, documentId: string) {
  const response = await fetch(API_BASE + "/v1/doctor/documents/" + documentId + "/finalize", {
    method: "POST",
    headers: requestHeaders(context, false)
  });
  return (await parse<{ data: any }>(response)).data;
}

export function absoluteApiUrl(path: string): string {
  return path.startsWith("http") ? path : API_BASE + path;
}


export async function fetchArtifact(context: LocalContext, path: string): Promise<Blob> {
  const response = await fetch(absoluteApiUrl(path), {
    headers: requestHeaders(context, false)
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.error || ("HTTP " + response.status));
  }
  return response.blob();
}

export async function downloadArtifact(
  context: LocalContext,
  path: string,
  filename: string
): Promise<void> {
  const blob = await fetchArtifact(context, path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function printPdf(context: LocalContext, path: string): Promise<void> {
  const blob = await fetchArtifact(context, path);
  const url = URL.createObjectURL(blob);
  const popup = window.open(url, "_blank");
  if (!popup) {
    URL.revokeObjectURL(url);
    throw new Error("Браузер заблокировал окно печати");
  }
  popup.addEventListener("load", () => popup.print(), { once: true });
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
