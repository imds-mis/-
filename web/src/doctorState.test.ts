import { describe, expect, it } from "vitest";
import { isDocumentEditable } from "./doctorState";

describe("doctor document lifecycle", () => {
  it("keeps draft editable before finalization", () => {
    expect(isDocumentEditable(null)).toBe(true);
  });

  it("locks document after finalization", () => {
    expect(isDocumentEditable({ sha256: "abc" })).toBe(false);
  });
});
