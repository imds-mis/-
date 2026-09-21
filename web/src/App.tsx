import { useEffect, useState } from "react";
import { defaultContext, LocalContext, saveContext } from "./api";
import DoctorPage from "./pages/DoctorPage";
import TemplatesPage from "./pages/TemplatesPage";

function ContextBar(props: { value: LocalContext; onChange: (next: LocalContext) => void }) {
  const fields: Array<[keyof LocalContext, string]> = [
    ["tenantId", "Tenant UUID"],
    ["userId", "User UUID"],
    ["branchId", "Branch UUID"],
    ["practitionerId", "Practitioner UUID"],
    ["specialtyCode", "Specialty code"]
  ];

  return (
    <section className="context-bar">
      <div>
        <strong>Реальный MIS контекст</strong>
        <span> Укажите фактические идентификаторы.</span>
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
  );
}

export default function App() {
  const [context, setContext] = useState<LocalContext>(() => defaultContext());
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => saveContext(context), [context]);

  useEffect(() => {
    const listener = () => setPath(window.location.pathname);
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, []);

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

      <ContextBar value={context} onChange={setContext} />

      <main>
        {path.startsWith("/settings/templates")
          ? <TemplatesPage context={context} />
          : <DoctorPage context={context} />}
      </main>
    </div>
  );
}
