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
    render(<PersonProfile people={people} events={[event("1", "one", "PEREZ ANA", "2024-01-01T10:00:00Z"), event("2", "two", "ANA PEREZ", "2024-02-01T10:00:00Z")]} loading={false} error={null} coincidences={[]} onRemove={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByRole("heading", {name: "Detalle de movimientos"})).toBeInTheDocument();
    expect(screen.getByRole("button", {name: /Descargar 2 registros de la selección en CSV/i})).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Persona"}));
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Ana Perez")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", {name: /Persona/i})).toHaveAttribute("aria-sort", "ascending");
  });

  it("muestra tablas largas de forma progresiva", () => {
    const events = Array.from({length: 101}, (_, index) => event(`${index}`, "one", "PEREZ ANA", `2024-01-${String(index % 28 + 1).padStart(2, "0")}T10:00:00Z`));
    const {container} = render(<PersonProfile people={[people[0]]} events={events} loading={false} error={null} coincidences={[]} onRemove={vi.fn()} onClear={vi.fn()} />);

    expect(container.querySelectorAll(".records-table tbody tr")).toHaveLength(100);
    fireEvent.click(screen.getByRole("button", {name: "Mostrar 1 más"}));
    expect(container.querySelectorAll(".records-table tbody tr")).toHaveLength(101);
  });

  it("abre un detalle citable y lo copia al portapapeles", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {value: {writeText}, configurable: true});
    const detailed = {...event("detail", "one", "PEREZ ANA", "2024-05-24T08:33:00Z"), entered_at: "2024-05-24T08:33:00Z", exited_at: "2024-05-24T17:12:00Z", destination: "Jefatura", purpose: "Reunión", raw_text: "Observación original", sources: [{url: "https://example.org/olivos-2024.pdf", path: "olivos/2024.pdf", page: 7}]} satisfies AccessEvent;
    render(<PersonProfile people={[people[0]]} events={[detailed]} loading={false} error={null} coincidences={[]} onRemove={vi.fn()} onClear={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", {name: /Ver detalle del registro/i}));
    expect(screen.getByRole("dialog", {name: "Detalle para citar"})).toBeInTheDocument();
    expect(screen.getByText(/respuesta oficial a un pedido de acceso a la información realizado por Poder Ciudadano/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Copiar detalle"}));
    expect(await screen.findByRole("button", {name: "Copiado"})).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("Fuente: Accesos a Olivos 2024"));
  });
});
