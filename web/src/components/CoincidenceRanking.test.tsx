import {fireEvent, render, screen, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import type {AccessEvent, CoincidenceResult, PersonSummary} from "../types";
import {CoincidenceRanking} from "./CoincidenceRanking";

const people: PersonSummary[] = [
  {entity_id: "person-1", canonical_name: "PEREZ ANA", normalized_name: "PEREZ ANA", document_type: "DNI", document_number: "30123456", record_count: 1, first_seen: "2024-05-24", last_seen: "2024-05-24", locations: ["casa-rosada"], record_types: ["visitor"], event_shard: "01"},
  {entity_id: "person-2", canonical_name: "GOMEZ LUIS", normalized_name: "GOMEZ LUIS", document_type: "DNI", document_number: "30234567", record_count: 1, first_seen: "2024-05-24", last_seen: "2024-05-24", locations: ["casa-rosada"], record_types: ["visitor"], event_shard: "02"},
];

function accessEvent(entityId: string, name: string, enteredAt: string, exitedAt: string | null): AccessEvent {
  return {record_id: `${entityId}-${enteredAt}`, entity_id: entityId, canonical_name: name, document_type: "DNI", document_number: null, location: "casa-rosada", record_type: "visitor", occurred_at: enteredAt, entered_at: enteredAt, exited_at: exitedAt, direction: null, device: null, destination: "Jefatura", purpose: null, activity: null, authorized_by: null, access_status: null, quality: "high", raw_text: "", sources: []};
}

const result: CoincidenceResult = {
  entityId: "person-3", canonicalName: "LOPEZ MARTA", documentType: "DNI", documentNumber: "30345678",
  days: 2, episodes: 2, overlapMinutes: 95, specificEpisodes: 2, latestDate: "2024-05-24",
  evidence: [{date: "2024-05-24", location: "casa-rosada", destination: "Jefatura", overlapMinutes: 50, overlapStart: "10:00", overlapEnd: "10:50", specificDestination: true, ownerName: "PEREZ ANA"}],
};

describe("CoincidenceRanking", () => {
  it("separa superposiciones seleccionadas de coincidencias automáticas", () => {
    const events = [
      accessEvent("person-1", "PEREZ ANA", "2024-05-24T10:00:00Z", "2024-05-24T11:00:00Z"),
      accessEvent("person-2", "GOMEZ LUIS", "2024-05-24T10:30:00Z", "2024-05-24T11:30:00Z"),
      accessEvent("person-2", "GOMEZ LUIS", "2024-05-25T10:30:00Z", null),
    ];
    const {container} = render(<CoincidenceRanking results={[result]} people={people} events={events} />);
    const disclosure = container.querySelector(".coincidence-disclosure");
    expect(screen.getByRole("heading", {name: "Coincidencias precisas: 2"})).toBeInTheDocument();
    expect(disclosure).not.toHaveAttribute("open");

    fireEvent.click(screen.getByText("Coincidencias precisas: 2"));
    expect(disclosure).toHaveAttribute("open");
    expect(screen.getByRole("heading", {name: "Entre las personas seleccionadas"})).toBeVisible();
    expect(screen.getByText(/presencia simultánea registrada, no necesariamente un encuentro/i)).toBeVisible();
    const selectedTable = screen.getByRole("table", {name: /superposiciones horarias entre/i});
    expect(within(selectedTable).getByText("Perez Ana y Gomez Luis")).toBeVisible();
    expect(within(selectedTable).getByText(/30 min/)).toBeVisible();
    expect(screen.getByRole("heading", {name: "Por destino y horario"})).toBeVisible();
    expect(screen.getByText(/Cálculo automático:/i)).toBeVisible();
    expect(screen.getByRole("table", {name: /calculadas automáticamente/i})).toBeVisible();
    expect(screen.getByText("Perez Ana ↔ Lopez Marta")).toBeVisible();
  });
});
