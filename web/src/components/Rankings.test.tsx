import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, expect, test, vi} from "vitest";
import {Rankings} from "./Rankings";

const DATA = {
  version: 1,
  definition: "Una presencia por persona, fecha y sede; se excluyen vehículos.",
  limit: 50,
  years: [{id: "2023", label: "2023", start_date: "2023-01-01", end_date: "2023-12-09"}],
  presidencies: [{id: "fernandez", label: "Alberto Fernández", start_date: "2019-12-10", end_date: "2023-12-09"}],
  rankings: {
    presidency: {fernandez: {all: [{entity_id: "per_1", canonical_name: "PEREZ ANA", document_type: "DNI", document_number: "30123456", daily_visits: 7, first_visit: "2023-01-01", last_visit: "2023-02-01", casa_rosada: 5, olivos: 2}], "casa-rosada": [], olivos: []}},
    year: {"2023": {all: [{entity_id: "per_1", canonical_name: "PEREZ ANA", document_type: "DNI", document_number: "30123456", daily_visits: 7, first_visit: "2023-01-01", last_visit: "2023-02-01", casa_rosada: 5, olivos: 2}], "casa-rosada": [], olivos: []}},
  },
};

afterEach(() => vi.restoreAllMocks());

test("muestra el ranking y permite cambiar agrupación y sede", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: true, json: async () => DATA}));
  render(<Rankings />);
  expect(await screen.findByText("PEREZ ANA")).toBeInTheDocument();
  expect(screen.getByText("7")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Años"}));
  expect(screen.getByLabelText("Período")).toHaveValue("2023");
  fireEvent.change(screen.getByLabelText("Sede"), {target: {value: "olivos"}});
  await waitFor(() => expect(screen.getByText("No hay registros para este período y sede.")).toBeInTheDocument());
});
