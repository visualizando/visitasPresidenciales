import {fireEvent, render, screen, within} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import type {AccessEvent, PersonSummary} from "../types";
import {PersonProfile} from "./PersonProfile";

const people: PersonSummary[] = [
  {entity_id: "one", canonical_name: "PEREZ ANA", normalized_name: "PEREZ ANA", document_type: "DNI", document_number: "30123456", record_count: 1, first_seen: "2024-01-01", last_seen: "2024-01-01", locations: ["olivos"], record_types: ["person"], event_shard: "01"},
  {entity_id: "two", canonical_name: "ANA PEREZ", normalized_name: "ANA PEREZ", document_type: "DNI", document_number: "30123456", record_count: 1, first_seen: "2024-02-01", last_seen: "2024-02-01", locations: ["olivos"], record_types: ["visitor"], event_shard: "02"},
];

function event(record_id: string, entity_id: string, canonical_name: string, occurred_at: string): AccessEvent {
  return {record_id, entity_id, canonical_name, document_type: "DNI", document_number: "30123456", location: "olivos", record_type: "person", occurred_at, entered_at: occurred_at, exited_at: null, direction: null, device: null, destination: null, purpose: null, activity: null, authorized_by: null, access_status: null, quality: "high", raw_text: "", sources: []};
}

describe("PersonProfile", () => {
  it("agrupa variantes y ordena la tabla por persona", () => {
    render(<PersonProfile people={people} events={[event("1", "one", "PEREZ ANA", "2024-01-01T10:00:00Z"), event("2", "two", "ANA PEREZ", "2024-02-01T10:00:00Z")]} loading={false} error={null} onRemove={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByRole("heading", {name: /2 variantes/i})).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Persona"}));
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Ana Perez")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", {name: /Persona/i})).toHaveAttribute("aria-sort", "ascending");
  });
});
