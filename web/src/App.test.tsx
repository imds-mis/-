import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

describe("MIS medical documents UI", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/doctor");
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => cleanup());

  it("shows the two clinical workspaces in navigation", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /Кабинет врача/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Шаблоны/i })).toBeInTheDocument();
  });

  it("keeps technical MIS identifiers out of the main clinical UI", () => {
    render(<App />);
    expect(screen.queryByText(/Tenant UUID/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Practitioner UUID/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Подключение/i })).toBeInTheDocument();
  });

  it("renders doctor workspace at /doctor without demo labels", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /Кабинет врача/i })).toBeInTheDocument();
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument();
  });

  it("renders template settings without raw JSON editor", () => {
    window.history.pushState({}, "", "/settings/templates");
    render(<App />);
    expect(screen.getByRole("heading", { name: /Медицинские шаблоны/i })).toBeInTheDocument();
    expect(screen.queryByText(/Поля шаблона \(JSON\)/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Специальность/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Тип приема/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Доступ для врача/i)).toBeInTheDocument();
  });
});


it("shows saved templates even when practitioner loading fails", async () => {
  localStorage.setItem("imds.tenantId", "t1");
  localStorage.setItem("imds.userId", "u1");
  localStorage.setItem("imds.branchId", "b1");
  window.history.pushState({}, "", "/settings/templates");

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/v1/admin/templates")) {
      return new Response(JSON.stringify({
        data: [{
          id: "template-1",
          name: "Осмотр",
          active: true,
          versions: [{ id: "v1", version: 1, status: "draft", fields: [] }],
          assignments: []
        }]
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.includes("/v1/integrations/mis/practitioners")) {
      return new Response(JSON.stringify({ detail: "MIS unavailable" }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
    return new Response(JSON.stringify({ data: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  });

  render(<App />);
  expect(await screen.findByText("Осмотр")).toBeInTheDocument();
});
