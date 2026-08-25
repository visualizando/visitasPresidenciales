import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {HeatmapChart} from "./HeatmapChart";

describe("HeatmapChart", () => {
  it("combina ambas sedes o muestra sólo la elegida", () => {
    const data = [
      {location: "casa-rosada" as const, weekday: 1, hour: 9, records: 2},
      {location: "olivos" as const, weekday: 1, hour: 9, records: 3},
    ];
    const {rerender} = render(<HeatmapChart data={data} location="all" />);
    expect(screen.getByRole("img", {name: "Mapa de calor de Ambas sedes"})).toBeInTheDocument();
    expect(screen.getByTitle("Ambas sedes · Lun, 9:00: 5 registros")).toBeInTheDocument();

    rerender(<HeatmapChart data={data} location="olivos" />);
    expect(screen.getByRole("img", {name: "Mapa de calor de Olivos"})).toBeInTheDocument();
    expect(screen.getByTitle("Olivos · Lun, 9:00: 3 registros")).toBeInTheDocument();
  });
});
