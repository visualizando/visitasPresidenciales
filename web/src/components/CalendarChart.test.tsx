import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {CalendarChart} from "./CalendarChart";

describe("CalendarChart", () => {
  it("suma tipos de registro por día y expone un resumen accesible", () => {
    const {container} = render(<CalendarChart location="casa-rosada" data={[
      {date: "2025-01-02", location: "casa-rosada", record_type: "visitor", records: 3, people: 2},
      {date: "2025-01-02", location: "casa-rosada", record_type: "movement", records: 4, people: 3},
      {date: "2025-01-03", location: "olivos", record_type: "person", records: 20, people: 10},
    ]} />);

    expect(screen.getByRole("img", {name: /2 de ene de 2025, con 7 registros/})).toBeInTheDocument();
    expect(container.querySelector('[title="2 de ene de 2025: 7 registros"]')).toBeInTheDocument();
  });
});
