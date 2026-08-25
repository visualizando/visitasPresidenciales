import {describe, expect, it} from "vitest";
import type {AccessEvent, PersonSummary} from "../types";
import {buildSelectedEventsCsv, selectedEventsFilename} from "./selectedEventsCsv";

function event(overrides: Partial<AccessEvent> = {}): AccessEvent {
  return {
    record_id: "record-1",
    entity_id: "person-1",
    canonical_name: "PÉREZ ANA",
    document_type: "DNI",
    document_number: "30123456",
    location: "olivos",
    record_type: "person",
    occurred_at: "2024-02-01T10:00:00Z",
    entered_at: "2024-02-01T10:00:00Z",
    exited_at: "2024-02-01T11:00:00Z",
    direction: null,
    device: null,
    destination: "DESPACHO, PRINCIPAL",
    purpose: "Reunión",
    activity: null,
    authorized_by: null,
    access_status: null,
    quality: "high",
    raw_text: "texto \"original\"",
    sources: [{url: "https://example.org/source.pdf", path: "olivos/source.pdf", page: 2}],
    ...overrides,
  };
}

describe("selectedEventsCsv", () => {
  it("exporta todas las columnas, escapa CSV y ordena cronológicamente", () => {
    const csv = buildSelectedEventsCsv([
      event(),
      event({record_id: "record-0", occurred_at: "2024-01-01T09:00:00Z", destination: "=2+2"}),
    ]);

    expect(csv.startsWith("\uFEFF\"record_id\"")).toBe(true);
    expect(csv.indexOf("record-0")).toBeLessThan(csv.indexOf("record-1"));
    expect(csv).toContain("\"DESPACHO, PRINCIPAL\"");
    expect(csv).toContain("\"texto \"\"original\"\"\"");
    expect(csv).toContain("\"'=2+2\"");
    expect(csv).toContain("\"https://example.org/source.pdf\"");
  });

  it("genera nombres legibles para una persona o una selección", () => {
    const person = {canonical_name: "PÉREZ, ANA", entity_id: "person-1"} as PersonSummary;
    expect(selectedEventsFilename([person])).toBe("accesos-perez-ana.csv");
    expect(selectedEventsFilename([person, {...person, entity_id: "person-2"}])).toBe("accesos-seleccion-2-personas.csv");
  });
});
