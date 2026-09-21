import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createTemplateVersion,
  disableTemplate,
  getPractitioners,
  getTemplates,
  inspectTemplate,
  LocalContext,
  Practitioner,
  publishTemplate,
  TemplateField,
  TemplateSummary,
  uploadTemplate
} from "../api";

const fallbackFields: TemplateField[] = [
  { id: "complaints", label: "Жалобы", type: "textarea", ai_source: "patient" },
  { id: "objective_status", label: "Объективный статус", type: "textarea", ai_source: "doctor" },
  { id: "diagnosis_text", label: "Диагноз", type: "text", ai_source: "doctor" },
  { id: "recommendations", label: "Рекомендации", type: "textarea", ai_source: "doctor" }
];

const visitTypes = [
  ["consultation", "Консультация"],
  ["primary", "Первичный прием"],
  ["follow_up", "Повторный прием"],
  ["examination", "Осмотр"],
  ["procedure", "Процедура"]
] as const;

function practitionerName(item: Practitioner) {
  return [item.last_name, item.first_name, item.middle_name].filter(Boolean).join(" ");
}

export default function TemplatesPage({ context }: { context: LocalContext }) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [name, setName] = useState("");
  const [visitType, setVisitType] = useState("consultation");
  const [specialtyCode, setSpecialtyCode] = useState(context.specialtyCode || "");
  const [practitionerId, setPractitionerId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState<TemplateField[]>(fallbackFields);
  const [enabledFields, setEnabledFields] = useState<Record<string, boolean>>(
    Object.fromEntries(fallbackFields.map((field) => [field.id, true]))
  );
  const [status, setStatus] = useState("");
  const [versionFiles, setVersionFiles] = useState<Record<string, File | null>>({});
  const [previewTemplateId, setPreviewTemplateId] = useState("");

  const contextReady = useMemo(
    () => Boolean(context.tenantId && context.userId && context.branchId),
    [context]
  );

  useEffect(() => {
    if (context.specialtyCode && !specialtyCode) setSpecialtyCode(context.specialtyCode);
  }, [context.specialtyCode]);

  async function refresh() {
    if (!contextReady) return;

    let templateError = "";
    try {
      const templateRows = await getTemplates(context);
      setTemplates(templateRows);
    } catch (error) {
      templateError = error instanceof Error ? error.message : String(error);
    }

    try {
      const practitionerRows = await getPractitioners(context);
      setPractitioners(practitionerRows);
    } catch {
      setPractitioners([]);
    }

    setStatus(templateError);
  }

  useEffect(() => {
    void refresh();
  }, [context.tenantId, context.userId, context.branchId]);

  async function chooseFile(nextFile: File | null) {
    setFile(nextFile);
    if (!nextFile || !contextReady) return;

    setStatus("Анализирую структуру DOCX…");
    try {
      const detected = await inspectTemplate(context, nextFile);
      const nextFields = detected.length ? detected : fallbackFields;
      setFields(nextFields);
      setEnabledFields(Object.fromEntries(nextFields.map((field) => [field.id, true])));
      if (!name) {
        setName(nextFile.name.replace(/\.docx$/i, ""));
      }
      setStatus("Поля документа определены. Проверьте их перед загрузкой.");
    } catch (error) {
      setFields(fallbackFields);
      setEnabledFields(Object.fromEntries(fallbackFields.map((field) => [field.id, true])));
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setStatus("Выберите DOCX файл");
      return;
    }

    const selectedFields = fields.filter((field) => enabledFields[field.id] !== false);
    if (!selectedFields.length) {
      setStatus("Выберите хотя бы одно поле документа");
      return;
    }

    try {
      await uploadTemplate(context, {
        name,
        file,
        fields: selectedFields,
        specialtyCode,
        practitionerId,
        visitType
      });
      setName("");
      setFile(null);
      setFields(fallbackFields);
      setEnabledFields(Object.fromEntries(fallbackFields.map((field) => [field.id, true])));
      setStatus("Шаблон сохранён. Он появится в библиотеке справа.");
      try {
        const templateRows = await getTemplates(context);
        setTemplates(templateRows);
      } catch (refreshError) {
        setStatus("Шаблон сохранён, но библиотеку не удалось обновить автоматически: " + (refreshError instanceof Error ? refreshError.message : String(refreshError)));
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">Настройки · Медицинские документы</div>
          <h1>Медицинские шаблоны</h1>
          <p>Загрузите DOCX один раз. Система определит клинические поля, а последующие изменения будут новой версией.</p>
        </div>
      </div>

      {!contextReady && (
        <div className="notice">
          Для локального запуска сначала откройте <strong>Подключение</strong> в верхней панели и укажите MIS-контекст.
        </div>
      )}

      <div className="two-column templates-layout">
        <section className="panel upload-panel">
          <div className="panel-title-row">
            <div>
              <h2>Добавить шаблон</h2>
              <div className="muted">DOCX → автоматическое определение полей → публикация</div>
            </div>
          </div>

          <form className="stack" onSubmit={submit}>
            <label>
              Название шаблона
              <input required value={name} placeholder="Например: Осмотр гинеколога" onChange={(event) => setName(event.target.value)} />
            </label>

            <div className="form-grid">
              <label>
                Специальность
                <select
                  aria-label="Специальность"
                  value={specialtyCode}
                  onChange={(event) => setSpecialtyCode(event.target.value)}
                >
                  <option value="">Все специальности</option>
                  {context.specialtyCode && (
                    <option value={context.specialtyCode}>{context.specialtyCode}</option>
                  )}
                </select>
              </label>

              <label>
                Тип приема
                <select
                  aria-label="Тип приема"
                  value={visitType}
                  onChange={(event) => setVisitType(event.target.value)}
                >
                  {visitTypes.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
            </div>

            <label>
              Доступ для врача
              <select
                aria-label="Доступ для врача"
                value={practitionerId}
                onChange={(event) => setPractitionerId(event.target.value)}
              >
                <option value="">Все врачи выбранной специальности</option>
                {practitioners.map((item) => (
                  <option key={item.id} value={item.id}>
                    {practitionerName(item)}
                    {item.practitioner_number ? " · " + item.practitioner_number : ""}
                  </option>
                ))}
              </select>
            </label>

            <label className="file-drop">
              <span>Файл DOCX</span>
              <input
                required
                type="file"
                accept=".docx"
                onChange={(event) => void chooseFile(event.target.files?.[0] || null)}
              />
              <small>{file ? file.name : "Выберите медицинский DOCX-шаблон"}</small>
            </label>

            <div className="detected-fields">
              <div className="field-section-title">
                <div>
                  <strong>Поля документа</strong>
                  <div className="muted">Система определяет их из структуры DOCX. Отключите ненужные.</div>
                </div>
                <span className="badge ok">{fields.filter((field) => enabledFields[field.id] !== false).length} полей</span>
              </div>

              <div className="field-checklist">
                {fields.map((field) => (
                  <label className="field-check" key={field.id}>
                    <input
                      type="checkbox"
                      checked={enabledFields[field.id] !== false}
                      onChange={(event) => setEnabledFields({
                        ...enabledFields,
                        [field.id]: event.target.checked
                      })}
                    />
                    <span>
                      <strong>{field.label || field.id}</strong>
                      <small>{field.type === "textarea" ? "Развернутый текст" : "Текст"}</small>
                    </span>
                    {field.ai_source && <span className="source-chip">{field.ai_source === "patient" ? "Пациент" : field.ai_source === "doctor" ? "Врач" : "Врач + пациент"}</span>}
                  </label>
                ))}
              </div>
            </div>

            <button className="primary large full-width" disabled={!contextReady || !file}>
              Сохранить шаблон
            </button>
          </form>

          {status && <div className="notice">{status}</div>}
        </section>

        <section className="panel template-library">
          <div className="panel-title-row">
            <div>
              <h2>Библиотека шаблонов</h2>
              <div className="muted">Опубликованные версии доступны врачам автоматически.</div>
            </div>
            <button onClick={() => void refresh()}>Обновить</button>
          </div>

          <div className="cards">
            {templates.map((template) => {
              const latest = template.versions[0];
              const previewOpen = previewTemplateId === template.id;
              return (
                <article className="card template-card" key={template.id}>
                  <div className="card-row">
                    <div>
                      <h3>{template.name}</h3>
                      <div className="template-meta">
                        <span>v{latest?.version ?? "—"}</span>
                        <span>•</span>
                        <span>{latest?.status === "published" ? "Опубликован" : "Черновик"}</span>
                      </div>
                    </div>
                    <span className={template.active ? "badge ok" : "badge"}>
                      {template.active ? "Активен" : "Отключен"}
                    </span>
                  </div>

                  <div className="assignment-summary">
                    {template.assignments.map((assignment, index) => (
                      <span className="assignment-chip" key={index}>
                        {assignment.specialty_code || "Все специальности"}
                        {assignment.visit_type ? " · " + assignment.visit_type : ""}
                      </span>
                    ))}
                  </div>

                  {previewOpen && latest && (
                    <div className="template-preview">
                      <strong>Поля v{latest.version}</strong>
                      <div className="preview-fields">
                        {(latest.fields || []).map((field) => (
                          <span key={field.id}>✓ {field.label || field.id}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="actions">
                    <button onClick={() => setPreviewTemplateId(previewOpen ? "" : template.id)}>
                      {previewOpen ? "Скрыть поля" : "Предпросмотр"}
                    </button>

                    {template.active && latest && (
                      <label className="version-button">
                        <input
                          type="file"
                          accept=".docx"
                          onChange={(event) => setVersionFiles({
                            ...versionFiles,
                            [template.id]: event.target.files?.[0] || null
                          })}
                        />
                        Выбрать новую версию
                      </label>
                    )}

                    {versionFiles[template.id] && latest && (
                      <button
                        onClick={async () => {
                          const nextFile = versionFiles[template.id];
                          if (!nextFile) return;
                          await createTemplateVersion(context, template.id, nextFile, latest.fields || []);
                          setVersionFiles({ ...versionFiles, [template.id]: null });
                          await refresh();
                        }}
                      >
                        Создать v{(latest.version || 0) + 1}
                      </button>
                    )}

                    {latest?.status !== "published" && template.active && (
                      <button
                        className="primary"
                        onClick={async () => {
                          await publishTemplate(context, template.id);
                          await refresh();
                        }}
                      >
                        Опубликовать
                      </button>
                    )}

                    {template.active && (
                      <button
                        className="quiet-danger"
                        onClick={async () => {
                          await disableTemplate(context, template.id);
                          await refresh();
                        }}
                      >
                        Отключить
                      </button>
                    )}
                  </div>
                </article>
              );
            })}

            {contextReady && templates.length === 0 && (
              <div className="empty empty-library">
                <strong>Шаблонов пока нет</strong>
                <span>Загрузите первый DOCX слева.</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
