import {render, screen, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {PurposeChart} from "./PurposeChart";

describe("PurposeChart", () => {
  it("distribuye destinos en un treemap y conserva una tabla accesible", () => {
    const {container} = render(<PurposeChart data={[
      {location: "casa-rosada", label: "Rivadavia 250", records: 20},
      {location: "casa-rosada", label: "Balcarce 24", records: 10},
      {location: "olivos", label: "Actividad oficial", records: 5},
    ]} />);

    expect(screen.getByRole("img", {name: /Treemap de destinos y motivos/})).toBeInTheDocument();
    expect(container.querySelectorAll(".treemap-chart--desktop .treemap-leaf")).toHaveLength(3);
    expect(screen.getByRole("table", {name: "Destinos y motivos por sede"})).toBeInTheDocument();
  });

  it("muestra en la leyenda sólo las sedes presentes", () => {
    render(<PurposeChart data={[{location: "olivos", label: "Actividad oficial", records: 5}]} />);
    const legend = screen.getByLabelText("Sedes");
    expect(within(legend).getByText("Olivos")).toBeInTheDocument();
    expect(within(legend).queryByText("Casa Rosada")).not.toBeInTheDocument();
  });
});
