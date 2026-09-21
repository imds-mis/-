import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  disableTemplate,
  getTemplates,
  LocalContext,
  publishTemplate,
  TemplateField,
  TemplateSummary,
  uploadTemplate
} from "../api";

const defaultFields: TemplateField[] = [
  {
    id: "complaints",
    label: "Жалобы",
    type: "textarea",
    ai_source: "patient",
    ai_hint: "Жалобы пациента, симптомы, локализация и длительность"
  },
  {
    id: "anamnesis_morbi",
    label: "Anamnesis morbi",
    type: "textarea",
    ai_source: "both",
    ai_hint: "История текущего заболевания"
  },
  {
    id: "objective_status",
    label: "Объективный статус",
    type: "textarea",
    ai_source: "doctor",
    ai_hint: "Объективные данные осмотра врача"
  },
  {
    id: "diagnosis_text",
    label: "Диагноз",
    type: "text",
    ai_source: "doctor",
    ai_hint: "Формулировка диагноза, только если врач явно ее произнес"
  },
  {
    id: "recommendations",
    label: "Рекомендации",
    type: "textarea",
    ai_source: "doctor",
    ai_hint: "Рекомендации врача"
  }
];

export default function TemplatesPage({ context }: { context: LocalContext }) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [name, setName] = useState("");
  const [visitType, setVisitType] = useState("consultation");
  const [file, setFile] = useState<File | null>(null);
  const [fieldsJson, setFieldsJson] = useState(JSON.stringify(defaultFields, null, 2));
  const [status, setStatus] = useState("");

  const contextReady = useMemo(
    () => Boolean(context.tenantId && context.userId && context.branchId),
    [context]
  );

  async function refresh() {
    if (!contextReady) return;
    try {
      setTemplates(await getTemplates(context));
      setStatus("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => {
    void refresh();
  }, [context.tenantId, context.userId, context.branchId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setStatus("Выберите DOCX файл");
      return;
    }

    try {
      const fields = JSON.parse(fieldsJson) as TemplateField[];
      await uploadTemplate(context, {
        name,
        file,
        fields,
        specialtyCode: context.specialtyCode,
        visitType
      });
      setName("");
      setFile(null);
      setStatus("Шаблон загружен. Опубликуйте его после проверки.");
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1>Шаблоны документов</h1>
          <p>DOCX загружается один раз. Изменения выпускаются новой версией.</p>
        </div>
      </div>

      <div className="two-column">
        <section className="panel">
          <h2>Загрузить шаблон</h2>
          <form className="stack" onSubmit={submit}>
            <label>
              Название
              <input required value={name} onChange={(event) => setName(event.target.value)} />
            </label>

            <label>
              Тип приема
              <input value={visitType} onChange={(event) => setVisitType(event.target.value)} />
            </label>

            <label>
              DOCX
              <input
                required
                type="file"
                accept=".docx"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
            </label>

            <label>
              Поля шаблона (JSON)
              <textarea
                rows={16}
                value={fieldsJson}
                onChange={(event) => setFieldsJson(event.target.value)}
              />
            </label>

            <button className="primary" disabled={!contextReady}>
              Загрузить шаблон
            </button>
          </form>

          {status && <div className="notice">{status}</div>}
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <h2>Загруженные шаблоны</h2>
            <button onClick={() => void refresh()}>Обновить</button>
          </div>

          <div className="cards">
            {templates.map((template) => {
              const latest = template.versions[0];
              return (
                <article className="card" key={template.id}>
                  <div className="card-row">
                    <div>
                      <h3>{template.name}</h3>
                      <div className="muted">
                        {"v" + (latest?.version ?? "—") + " · " + (latest?.status ?? "нет версии")}
                      </div>
                    </div>
                    <span className={template.active ? "badge ok" : "badge"}>
                      {template.active ? "Активен" : "Отключен"}
                    </span>
                  </div>

                  <div className="muted">
                    {template.assignments.map((assignment, index) => (
                      <div key={index}>
                        {assignment.specialty_code || "Все специальности"}
                        {assignment.visit_type ? " · " + assignment.visit_type : ""}
                      </div>
                    ))}
                  </div>

                  <div className="actions">
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
              <div className="empty">Шаблоны еще не загружены.</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
