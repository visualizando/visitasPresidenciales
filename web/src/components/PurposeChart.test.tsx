import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {PurposeChart} from "./PurposeChart";

describe("PurposeChart", () => {
  it("empaqueta destinos por sede y conserva una tabla accesible", () => {
    const {container} = render(<PurposeChart data={[
      {location: "casa-rosada", label: "Rivadavia 250", records: 20},
      {location: "casa-rosada", label: "Balcarce 24", records: 10},
      {location: "olivos", label: "Actividad oficial", records: 5},
    ]} />);

    expect(screen.getByRole("img", {name: /Circle pack de destinos y motivos/})).toBeInTheDocument();
    expect(container.querySelectorAll(".pack-leaf")).toHaveLength(3);
    expect(screen.getByRole("table", {name: "Destinos y motivos por sede"})).toBeInTheDocument();
  });
});
