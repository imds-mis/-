import { useEffect, useMemo, useState } from "react";
import { defaultContext, LocalContext, saveContext } from "./api";
import DoctorPage from "./pages/DoctorPage";
import TemplatesPage from "./pages/TemplatesPage";

function ConnectionPanel(props: {
  open: boolean;
  value: LocalContext;
  onChange: (next: LocalContext) => void;
  onClose: () => void;
}) {
  const fields: Array<[keyof LocalContext, string]> = [
    ["tenantId", "Tenant UUID"],
    ["userId", "User UUID"],
    ["branchId", "Branch UUID"],
    ["practitionerId", "Practitioner UUID"],
    ["specialtyCode", "Specialty code"]
  ];

  if (!props.open) return null;

  return (
    <div className="connection-backdrop" onClick={props.onClose}>
      <section className="connection-panel" onClick={(event) => event.stopPropagation()}>
        <div className="panel-title-row">
          <div>
            <h2>Подключение к MIS</h2>
            <p className="muted">
              Эти идентификаторы нужны только для локального запуска. В production они приходят из авторизации автоматически.
            </p>
          </div>
          <button onClick={props.onClose}>Закрыть</button>
        </div>

        <div className="context-grid">
          {fields.map(([key, label]) => (
            <label key={key}>
              <span>{label}</span>
              <input
                value={props.value[key]}
                onChange={(event) => props.onChange({ ...props.value, [key]: event.target.value })}
              />
            </label>
          ))}
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [context, setContext] = useState<LocalContext>(() => defaultContext());
  const [path, setPath] = useState(window.location.pathname);
  const [connectionOpen, setConnectionOpen] = useState(false);

  useEffect(() => saveContext(context), [context]);

  useEffect(() => {
    const listener = () => setPath(window.location.pathname);
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, []);

  const connected = useMemo(
    () => Boolean(context.tenantId && context.userId && context.branchId),
    [context]
  );

  function navigate(next: string) {
    window.history.pushState({}, "", next);
    setPath(next);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">IMDS</div>
          <div className="subtitle">Medical Documents</div>
        </div>

        <nav>
          <button className="connection-button" onClick={() => setConnectionOpen(true)}>
            {connected ? "Подключение ✓" : "Подключение"}
          </button>

          <a
            href="/doctor"
            onClick={(event) => {
              event.preventDefault();
              navigate("/doctor");
            }}
          >
            Кабинет врача
          </a>

          <a
            href="/settings/templates"
            onClick={(event) => {
              event.preventDefault();
              navigate("/settings/templates");
            }}
          >
            Шаблоны
          </a>
        </nav>
      </header>

      <ConnectionPanel
        open={connectionOpen}
        value={context}
        onChange={setContext}
        onClose={() => setConnectionOpen(false)}
      />

      <main>
        {path.startsWith("/settings/templates")
          ? <TemplatesPage context={context} />
          : <DoctorPage context={context} />}
      </main>
    </div>
  );
}
