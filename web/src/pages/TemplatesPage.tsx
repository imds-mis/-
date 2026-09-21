import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ClinicHeaderSettings,
  createTemplateVersion,
  disableTemplate,
  getClinicHeader,
  getPractitioners,
  getTemplates,
  inspectTemplate,
  LocalContext,
  Practitioner,
  previewTemplatePdf,
  publishTemplate,
  saveClinicHeader,
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

const emptyHeader: ClinicHeaderSettings = {
  clinic_name: "",
  bin: "",
  address: "",
  phone: "",
  license_text: "",
  extra_line: "",
  footer_text: "",
  has_logo: false
};

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

  const [clinicHeader, setClinicHeader] = useState<ClinicHeaderSettings>(emptyHeader);
  const [clinicHeaderOpen, setClinicHeaderOpen] = useState(false);
  const [clinicLogo, setClinicLogo] = useState<File | null>(null);
  const [clinicHeaderStatus, setClinicHeaderStatus] = useState("");

  const [previewUrl, setPreviewUrl] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");

  const contextReady = useMemo(
    () => Boolean(context.tenantId && context.userId && context.branchId),
    [context]
  );

  useEffect(() => {
    if (context.specialtyCode && !specialtyCode) setSpecialtyCode(context.specialtyCode);
  }, [context.specialtyCode]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

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

    try {
      setClinicHeader(await getClinicHeader(context));
    } catch {
      setClinicHeader(emptyHeader);
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
      setStatus("Шаблон сохранён. Он появился в библиотеке справа.");
      try {
        setTemplates(await getTemplates(context));
      } catch (refreshError) {
        setStatus("Шаблон сохранён, но библиотеку не удалось обновить автоматически: " + (refreshError instanceof Error ? refreshError.message : String(refreshError)));
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function saveHeader(event: FormEvent) {
    event.preventDefault();
    setClinicHeaderStatus("Сохраняю шапку…");
    try {
      const saved = await saveClinicHeader(context, {
        clinic_name: clinicHeader.clinic_name,
        bin: clinicHeader.bin,
        address: clinicHeader.address,
        phone: clinicHeader.phone,
        license_text: clinicHeader.license_text,
        extra_line: clinicHeader.extra_line,
        footer_text: clinicHeader.footer_text,
        logo: clinicLogo
      });
      setClinicHeader(saved);
      setClinicLogo(null);
      setClinicHeaderStatus("Шапка клиники сохранена и будет применяться ко всем документам.");
    } catch (error) {
      setClinicHeaderStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function openPreview(template: TemplateSummary) {
    setStatus("Формирую PDF-предпросмотр…");
    try {
      const blob = await previewTemplatePdf(context, template.id);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const url = URL.createObjectURL(blob);
      setPreviewUrl(url);
      setPreviewTitle(template.name);
      setStatus("");
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

        <button
          className="header-settings-button"
          onClick={() => setClinicHeaderOpen((value) => !value)}
        >
          Шапка клиники
        </button>
      </div>

      {clinicHeaderOpen && (
        <section className="panel clinic-header-panel">
          <div className="panel-title-row">
            <div>
              <h2>Шапка клиники</h2>
              <div className="muted">Один раз настраивается для всех медицинских документов.</div>
            </div>
            <span className={clinicHeader.clinic_name ? "badge ok" : "badge"}>
              {clinicHeader.clinic_name ? "Настроена" : "Не настроена"}
            </span>
          </div>

          <form className="stack" onSubmit={saveHeader}>
            <div className="form-grid">
              <label>
                Название клиники
                <input
                  value={clinicHeader.clinic_name}
                  placeholder="Amanat Med"
                  onChange={(event) => setClinicHeader({ ...clinicHeader, clinic_name: event.target.value })}
                />
              </label>
              <label>
                БИН
                <input
                  value={clinicHeader.bin}
                  placeholder="123456789012"
                  onChange={(event) => setClinicHeader({ ...clinicHeader, bin: event.target.value })}
                />
              </label>
              <label>
                Адрес
                <input
                  value={clinicHeader.address}
                  placeholder="г. Алматы, ..."
                  onChange={(event) => setClinicHeader({ ...clinicHeader, address: event.target.value })}
                />
              </label>
              <label>
                Телефон
                <input
                  value={clinicHeader.phone}
                  placeholder="+7 ..."
                  onChange={(event) => setClinicHeader({ ...clinicHeader, phone: event.target.value })}
                />
              </label>
              <label>
                Лицензия
                <input
                  value={clinicHeader.license_text}
                  placeholder="Лицензия №..."
                  onChange={(event) => setClinicHeader({ ...clinicHeader, license_text: event.target.value })}
                />
              </label>
              <label>
                Дополнительная строка
                <input
                  value={clinicHeader.extra_line}
                  placeholder="Медицинский центр"
                  onChange={(event) => setClinicHeader({ ...clinicHeader, extra_line: event.target.value })}
                />
              </label>
            </div>

            <label>
              Подвал документа
              <input
                value={clinicHeader.footer_text}
                placeholder="Адрес / сайт / служебная строка"
                onChange={(event) => setClinicHeader({ ...clinicHeader, footer_text: event.target.value })}
              />
            </label>

            <label className="file-drop compact-logo-upload">
              <span>Логотип клиники</span>
              <input
                type="file"
                accept="image/png,image/jpeg"
                onChange={(event) => setClinicLogo(event.target.files?.[0] || null)}
              />
              <small>
                {clinicLogo
                  ? clinicLogo.name
                  : clinicHeader.has_logo
                    ? "Логотип уже загружен. Выберите файл, чтобы заменить."
                    : "PNG или JPEG"}
              </small>
            </label>

            <div className="actions">
              <button className="primary" type="submit">Сохранить шапку</button>
              <button type="button" onClick={() => setClinicHeaderOpen(false)}>Закрыть</button>
            </div>
          </form>

          {clinicHeaderStatus && <div className="notice">{clinicHeaderStatus}</div>}
        </section>
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

                  {latest && (
                    <div className="template-preview-summary">
                      {(latest.fields || []).slice(0, 5).map((field) => (
                        <span key={field.id}>✓ {field.label || field.id}</span>
                      ))}
                      {(latest.fields || []).length > 5 && (
                        <span>+ ещё {(latest.fields || []).length - 5}</span>
                      )}
                    </div>
                  )}

                  <div className="actions">
                    <button className="preview-primary" onClick={() => void openPreview(template)}>
                      Предпросмотр PDF
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

      {previewUrl && (
        <div className="preview-backdrop" onClick={() => setPreviewUrl("")}>
          <section className="preview-modal" onClick={(event) => event.stopPropagation()}>
            <div className="panel-title-row">
              <div>
                <h2>Предпросмотр документа</h2>
                <div className="muted">{previewTitle}</div>
              </div>
              <div className="actions">
                <a href={previewUrl} target="_blank" rel="noreferrer">Открыть отдельно</a>
                <button onClick={() => setPreviewUrl("")}>Закрыть</button>
              </div>
            </div>
            <div className="a4-preview-frame">
              <iframe title={"Предпросмотр " + previewTitle} src={previewUrl} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
