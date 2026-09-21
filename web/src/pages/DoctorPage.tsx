import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  acceptSuggestion,
  createDocument,
  createLocalPatient,
  createVisitSession,
  FieldSuggestion,
  finalizeDocument,
  finishVisitSession,
  downloadArtifact,
  getEligibleTemplates,
  getLocalPatients,
  getProtocols,
  LocalContext,
  Patient,
  searchIcd,
  TemplateField,
  printPdf,
  TranscriptTurn,
  updateDocumentFields,
  uploadAudioChunk
} from "../api";
import { isDocumentEditable } from "../doctorState";

type EligibleTemplate = {
  id: string;
  name: string;
  version: number;
  fields: TemplateField[];
};

export default function DoctorPage({ context }: { context: LocalContext }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [templates, setTemplates] = useState<EligibleTemplate[]>([]);
  const [patientId, setPatientId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [visitType, setVisitType] = useState("primary");
  const [documentId, setDocumentId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [suggestions, setSuggestions] = useState<FieldSuggestion[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [icdQuery, setIcdQuery] = useState("");
  const [icdResults, setIcdResults] = useState<Array<{ code: string; title: string }>>([]);
  const [selectedIcd, setSelectedIcd] = useState<{ code: string; title: string } | null>(null);
  const [protocols, setProtocols] = useState<any[]>([]);
  const [selectedProtocolId, setSelectedProtocolId] = useState("");
  const [selectedProtocolItems, setSelectedProtocolItems] = useState<Record<string, boolean>>({});
  const [finalDocument, setFinalDocument] = useState<any>(null);
  const [patientFormOpen, setPatientFormOpen] = useState(false);
  const [patientForm, setPatientForm] = useState({
    last_name: "",
    first_name: "",
    middle_name: "",
    iin: "",
    medical_record_number: "",
    date_of_birth: "",
    phone: ""
  });
  const recorder = useRef<MediaRecorder | null>(null);
  const chunkCounter = useRef(0);

  const selectedPatient = patients.find((patient) => patient.id === patientId);
  const selectedTemplate = templates.find((template) => template.id === templateId);

  const ready = useMemo(
    () => Boolean(
      context.tenantId &&
      context.userId &&
      context.branchId &&
      context.practitionerId
    ),
    [context]
  );

  useEffect(() => {
    if (!ready) return;

    void getLocalPatients(context)
      .then((patientRows) => setPatients(patientRows))
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));

    void getEligibleTemplates(context, visitType)
      .then((templateRows) => {
        setTemplates(templateRows);
        if (templateId && !templateRows.some((item) => item.id === templateId)) {
          setTemplateId("");
        }
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [
    context.tenantId,
    context.userId,
    context.branchId,
    context.practitionerId,
    context.specialtyCode,
    visitType
  ]);

  async function addPatient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const created = await createLocalPatient(context, patientForm);
      setPatients((current) => [...current, created].sort((a, b) =>
        (a.last_name + a.first_name).localeCompare(b.last_name + b.first_name, "ru")
      ));
      setPatientId(created.id);
      setPatientForm({
        last_name: "",
        first_name: "",
        middle_name: "",
        iin: "",
        medical_record_number: "",
        date_of_birth: "",
        phone: ""
      });
      setPatientFormOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function mergeSuggestions(items: FieldSuggestion[]) {
    setSuggestions(items);
  }

  async function startVisit() {
    if (!selectedPatient || !selectedTemplate) return;

    setError("");

    try {
      const document = await createDocument(
        context,
        selectedTemplate.id,
        selectedPatient,
        visitType
      );
      setDocumentId(document.id);

      const visit = await createVisitSession(
        context,
        document.id,
        selectedPatient.id
      );
      setSessionId(visit.id);

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Браузер не поддерживает запись с микрофона");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      recorder.current = mediaRecorder;

      mediaRecorder.ondataavailable = async (event) => {
        if (!event.data.size) return;

        const chunkId =
          "chunk-" +
          Date.now() +
          "-" +
          String(chunkCounter.current++);

        try {
          const result = await uploadAudioChunk(
            context,
            visit.id,
            chunkId,
            event.data
          );
          setTranscript(result.transcript);
          mergeSuggestions(result.suggestions);
        } catch (reason) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      };

      mediaRecorder.start(5000);
      setRecording(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function finishConversation() {
    const active = recorder.current;

    if (active && active.state !== "inactive") {
      await new Promise<void>((resolve) => {
        active.addEventListener(
          "stop",
          () => resolve(),
          { once: true }
        );
        active.stop();
        active.stream.getTracks().forEach((track) => track.stop());
      });
    }

    setRecording(false);

    if (!sessionId) return;

    try {
      const result = await finishVisitSession(context, sessionId);
      setTranscript(result.transcript);
      mergeSuggestions(result.suggestions);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function accept(fieldId: string) {
    if (!sessionId) return;

    try {
      const result = await acceptSuggestion(context, sessionId, fieldId);
      setValues((current) => ({
        ...current,
        [fieldId]: String(result.value ?? "")
      }));
      setSuggestions((current) =>
        current.map((item) =>
          item.field_id === fieldId
            ? { ...item, status: "accepted" }
            : item
        )
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function saveFields() {
    if (!documentId || !isDocumentEditable(finalDocument)) return;

    try {
      await updateDocumentFields(context, documentId, values);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function runIcdSearch() {
    try {
      setIcdResults(await searchIcd(context, icdQuery));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function chooseIcd(item: { code: string; title: string }) {
    setSelectedIcd(item);
    setValues((current) => ({
      ...current,
      diagnosis_text: item.code + " — " + item.title
    }));

    try {
      const rows = await getProtocols(context, item.code);
      setProtocols(rows);
      setSelectedProtocolId("");
      setSelectedProtocolItems({});
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function applyProtocolSelection() {
    const protocol = protocols.find((item) => item.id === selectedProtocolId);
    if (!protocol) return;

    const selected = (protocol.items || [])
      .filter((item: any, index: number) => selectedProtocolItems[String(index)])
      .map((item: any) => item.title || item.description || item.type)
      .filter(Boolean);

    const targetField = fields.some((field) => field.id === "treatment_plan")
      ? "treatment_plan"
      : fields.some((field) => field.id === "recommendations")
        ? "recommendations"
        : "";

    if (!targetField) {
      setError("В шаблоне нет поля treatment_plan или recommendations для выбранного протокола");
      return;
    }

    const block = [
      "Клинический протокол: " + protocol.title + " · v" + String(protocol.version),
      ...selected.map((title: string) => "• " + title)
    ].join("\n");

    setValues((current) => ({
      ...current,
      [targetField]: current[targetField]
        ? current[targetField] + "\n\n" + block
        : block
    }));
  }

  async function finalize() {
    if (!documentId || !isDocumentEditable(finalDocument)) return;

    try {
      await saveFields();
      const result = await finalizeDocument(context, documentId);
      setFinalDocument(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  const fields = selectedTemplate?.fields || [];
  const editable = isDocumentEditable(finalDocument);

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1>Кабинет врача</h1>
          <p>
            Пациент → разговор → AI-черновик → проверка врача → документ.
          </p>
        </div>
        {recording && <span className="recording">● Идет запись</span>}
      </div>

      {error && <div className="notice error">{error}</div>}

      <section className="panel">
        <div className="form-grid doctor-top-grid">
          <div className="patient-selector-block">
            <label>
              Пациент
              <select
                value={patientId}
                onChange={(event) => setPatientId(event.target.value)}
                disabled={Boolean(documentId)}
              >
                <option value="">Выберите пациента</option>
                {patients.map((patient) => (
                  <option value={patient.id} key={patient.id}>
                    {[patient.last_name, patient.first_name, patient.middle_name]
                      .filter(Boolean)
                      .join(" ")}
                    {patient.medical_record_number
                      ? " · " + patient.medical_record_number
                      : ""}
                  </option>
                ))}
              </select>
            </label>
            {!documentId && (
              <button type="button" onClick={() => setPatientFormOpen((value) => !value)}>
                {patientFormOpen ? "Скрыть форму" : "+ Новый пациент"}
              </button>
            )}
          </div>

          <label>
            Тип приема
            <select
              aria-label="Тип приема"
              value={visitType}
              onChange={(event) => setVisitType(event.target.value)}
              disabled={Boolean(documentId)}
            >
              <option value="primary">Первичный прием</option>
              <option value="follow_up">Повторный прием</option>
              <option value="consultation">Консультация</option>
              <option value="examination">Осмотр</option>
              <option value="procedure">Процедура</option>
            </select>
          </label>

          <label>
            Протокол осмотра
            <select
              value={templateId}
              onChange={(event) => setTemplateId(event.target.value)}
              disabled={Boolean(documentId)}
            >
              <option value="">Выберите шаблон</option>
              {templates.map((template) => (
                <option value={template.id} key={template.id}>
                  {template.name + " · v" + String(template.version)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {patientFormOpen && !documentId && (
          <form className="local-patient-form" onSubmit={addPatient}>
            <div className="form-grid">
              <label>Фамилия<input required value={patientForm.last_name} onChange={(event) => setPatientForm({ ...patientForm, last_name: event.target.value })} /></label>
              <label>Имя<input required value={patientForm.first_name} onChange={(event) => setPatientForm({ ...patientForm, first_name: event.target.value })} /></label>
              <label>Отчество<input value={patientForm.middle_name} onChange={(event) => setPatientForm({ ...patientForm, middle_name: event.target.value })} /></label>
              <label>ИИН<input value={patientForm.iin} onChange={(event) => setPatientForm({ ...patientForm, iin: event.target.value })} /></label>
              <label>№ медкарты<input value={patientForm.medical_record_number} onChange={(event) => setPatientForm({ ...patientForm, medical_record_number: event.target.value })} /></label>
              <label>Дата рождения<input type="date" value={patientForm.date_of_birth} onChange={(event) => setPatientForm({ ...patientForm, date_of_birth: event.target.value })} /></label>
              <label>Телефон<input value={patientForm.phone} onChange={(event) => setPatientForm({ ...patientForm, phone: event.target.value })} /></label>
            </div>
            <div className="actions">
              <button className="primary" type="submit">Сохранить пациента</button>
              <button type="button" onClick={() => setPatientFormOpen(false)}>Отмена</button>
            </div>
          </form>
        )}

        {!documentId && (
          <button
            className="primary large"
            disabled={!patientId || !templateId || !ready}
            onClick={() => void startVisit()}
          >
            Начать прием и включить микрофон
          </button>
        )}

        {recording && (
          <button
            className="danger large"
            onClick={() => void finishConversation()}
          >
            Завершить разговор
          </button>
        )}
      </section>

      {documentId && (
        <div className="review-grid">
          <section className="panel">
            <h2>Разговор</h2>
            <div className="transcript">
              {transcript.map((turn) => (
                <div
                  className={"turn " + turn.speaker}
                  key={turn.id}
                >
                  <strong>
                    {turn.speaker === "doctor" ? "Врач" : "Пациент"}
                  </strong>
                  <p>{turn.text}</p>
                </div>
              ))}

              {transcript.length === 0 && (
                <div className="empty">
                  Ожидается распознавание речи…
                </div>
              )}
            </div>
          </section>

          <section className="panel">
            <h2>Протокол осмотра</h2>

            <div className="stack">
              {fields.map((field) => {
                const suggestion = suggestions.find(
                  (item) => item.field_id === field.id
                );

                return (
                  <div className="clinical-field" key={field.id}>
                    <div className="field-title">
                      <label htmlFor={"field-" + field.id}>
                        {field.label || field.id}
                      </label>

                      {suggestion && (
                        <span className="confidence">
                          {String(Math.round((suggestion.confidence || 0) * 100)) + "% AI"}
                        </span>
                      )}
                    </div>

                    {field.type === "textarea" ? (
                      <textarea
                        id={"field-" + field.id}
                        rows={4}
                        value={values[field.id] || ""}
                        disabled={!editable}
                        onChange={(event) =>
                          setValues({
                            ...values,
                            [field.id]: event.target.value
                          })
                        }
                      />
                    ) : (
                      <input
                        id={"field-" + field.id}
                        value={values[field.id] || ""}
                        disabled={!editable}
                        onChange={(event) =>
                          setValues({
                            ...values,
                            [field.id]: event.target.value
                          })
                        }
                      />
                    )}

                    {suggestion?.status === "suggested" && (
                      <div className="suggestion-box">
                        <div><strong>AI-черновик:</strong> {String(suggestion.value ?? "")}</div>
                        <div className="actions">
                          <button
                            className="primary"
                            onClick={() => void accept(field.id)}
                          >
                            Принять AI-черновик
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              {editable ? (
                <button onClick={() => void saveFields()}>
                  Сохранить заполнение
                </button>
              ) : (
                <div className="notice success">
                  Документ завершён. Для изменений создайте новый приём/коррекцию.
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {documentId && (
        <section className="panel">
          <h2>МКБ-10 и клинический протокол</h2>

          <div className="search-row">
            <input
              placeholder="Код или название МКБ-10"
              value={icdQuery}
              disabled={!editable}
              onChange={(event) => setIcdQuery(event.target.value)}
            />
            <button disabled={!editable} onClick={() => void runIcdSearch()}>
              Найти
            </button>
          </div>

          <div className="icd-results">
            {icdResults.map((item) => (
              <button
                className={
                  selectedIcd?.code === item.code
                    ? "selected-item"
                    : ""
                }
                key={item.code}
                onClick={() => void chooseIcd(item)}
              >
                <strong>{item.code}</strong>{" "}
                {item.title}
              </button>
            ))}
          </div>

          {selectedIcd && (
            <div className="protocol-list">
              <h3>{"Протоколы для " + selectedIcd.code}</h3>

              {protocols.map((protocol) => (
                <details
                  key={protocol.id}
                  open={selectedProtocolId === protocol.id}
                  onToggle={(event) => {
                    if ((event.currentTarget as HTMLDetailsElement).open) {
                      setSelectedProtocolId(protocol.id);
                      setSelectedProtocolItems({});
                    }
                  }}
                >
                  <summary>
                    {protocol.title + " · v" + String(protocol.version)}
                  </summary>

                  <div className="protocol-items">
                    {(protocol.items || []).map(
                      (item: any, index: number) => (
                        <label key={index}>
                          <input
                            type="checkbox"
                            checked={Boolean(selectedProtocolItems[String(index)])}
                            onChange={(event) => setSelectedProtocolItems({
                              ...selectedProtocolItems,
                              [String(index)]: event.target.checked
                            })}
                          />
                          {" "}
                          {item.title || item.description || item.type}
                        </label>
                      )
                    )}
                    <button
                      className="primary"
                      onClick={() => applyProtocolSelection()}
                    >
                      Добавить выбранное в план
                    </button>
                  </div>
                </details>
              ))}

              {protocols.length === 0 && (
                <div className="empty">
                  Связанный опубликованный протокол не найден.
                </div>
              )}
              </div>
            </>
          )}
        </section>
      )}

      {documentId && !recording && (
        <section className="panel final-panel">
          {editable && (
            <button
              className="primary large"
              onClick={() => void finalize()}
            >
              Завершить прием и сформировать документ
            </button>
          )}

          {finalDocument && (
            <>
              <div className="finalized-banner">
                <strong>Приём завершён</strong>
                <span>Документ зафиксирован и больше не редактируется.</span>
              </div>
              <div className="final-actions">
              <button onClick={() => void printPdf(context, finalDocument.pdf_download_url)}>
                Открыть / печать PDF
              </button>
              <button onClick={() => void downloadArtifact(context, finalDocument.pdf_download_url, documentId + ".pdf")}>
                Скачать PDF
              </button>
              <button onClick={() => void downloadArtifact(context, finalDocument.docx_download_url, documentId + ".docx")}>
                Скачать DOCX
              </button>
              {finalDocument.verification_url && (
                <a
                  target="_blank"
                  rel="noreferrer"
                  href={finalDocument.verification_url}
                >
                  QR-проверка
                </a>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
