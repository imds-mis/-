import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "./App";

describe("MIS medical documents UI", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/doctor");
  });

  it("shows the two real workspaces in navigation", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /Кабинет врача/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Шаблоны/i })).toBeInTheDocument();
  });

  it("renders doctor workspace at /doctor without demo labels", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /Кабинет врача/i })).toBeInTheDocument();
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument();
  });

  it("renders template settings at /settings/templates", () => {
    window.history.pushState({}, "", "/settings/templates");
    render(<App />);
    expect(screen.getByRole("heading", { name: /Шаблоны документов/i })).toBeInTheDocument();
  });
});
