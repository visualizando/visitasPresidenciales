import {render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {SearchResults} from "./SearchResults";
import type {PersonSummary} from "../types";

const person: PersonSummary = {
  entity_id: "per_1",
  canonical_name: "PEREZ ANA",
  normalized_name: "PEREZ ANA",
  document_type: "DNI",
  document_number: "30123456",
  record_count: 12,
  first_seen: "2023-01-01T10:00:00Z",
  last_seen: "2024-01-01T10:00:00Z",
  locations: ["olivos"],
  record_types: ["person"],
  event_shard: "ab",
};

describe("SearchResults", () => {
  it("orienta antes de buscar", () => {
    render(<SearchResults query="" results={[]} selectedIds={new Set()} loading={false} error={null} onToggle={vi.fn()} />);
    expect(screen.getByText(/al menos dos letras/i)).toBeInTheDocument();
  });

  it("muestra documento completo y botón accesible", () => {
    render(<SearchResults query="Ana" results={[person]} selectedIds={new Set()} loading={false} error={null} onToggle={vi.fn()} />);
    expect(screen.getByRole("button", {name: /Perez Ana/i})).toHaveTextContent("30123456");
  });

  it("expone la selección múltiple como estado del botón", () => {
    const onToggle = vi.fn();
    render(<SearchResults query="Ana" results={[person]} selectedIds={new Set([person.entity_id])} loading={false} error={null} onToggle={onToggle} />);
    const result = screen.getByRole("button", {name: /Perez Ana/i});
    expect(result).toHaveAttribute("aria-pressed", "true");
    result.click();
    expect(onToggle).toHaveBeenCalledWith(person);
  });

  it("explica cómo salir de un resultado vacío", () => {
    render(<SearchResults query="Nadie" results={[]} selectedIds={new Set()} loading={false} error={null} onToggle={vi.fn()} />);
    expect(screen.getByText(/probá sin filtros/i)).toBeInTheDocument();
  });
});
