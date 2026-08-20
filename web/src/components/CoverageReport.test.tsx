import {render, screen} from "@testing-library/react";
import {afterEach, expect, test, vi} from "vitest";
import {CoverageReport} from "./CoverageReport";

afterEach(() => vi.restoreAllMocks());

test("muestra los períodos sin registros y explica archivos en cuarentena", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: true, json: async () => ({
    version: 1,
    first_date: "2023-01-01",
    last_date: "2023-03-31",
    older_period: {end_date: "2023-01-01", reason: "No hay registros anteriores."},
    summary: {active_files: 3, quarantined_files: 1, missing_files: 0, zero_record_files: 0},
    locations: [{location: "casa-rosada", months_with_data: 2, gaps: [{start_month: "2023-02", end_month: "2023-02", reason: "Sin archivo."}]}, {location: "olivos", months_with_data: 0, gaps: []}],
    file_issues: [{path: "escaneado.pdf", location: "olivos", year: 2023, month: 2, status: "quarantined", parser: "no-legible-o-formato-desconocido-v1", reason: "El archivo está disponible, pero no tiene texto legible."}],
  })}));
  render(<CoverageReport />);
  expect(await screen.findByText("Qué falta y por qué")).toBeInTheDocument();
  expect(screen.getByText("feb 2023")).toBeInTheDocument();
  expect(screen.getByText(/Archivos sin registros o con problemas/)).toBeInTheDocument();
});
