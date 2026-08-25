import {fireEvent, render, screen} from "@testing-library/react";
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
    expect(container.querySelector('[data-date="2025-01-02"] .calendar-day-number')).toHaveTextContent("2");
    expect(container.querySelector<HTMLElement>('[data-date="2025-02-01"]')).toHaveStyle({transform: "translateX(3px)"});
    expect(container.querySelector<HTMLElement>('[data-month="2025-01"]')).toHaveStyle({gridColumnStart: "2"});
  });

  it("divide por color y señala los días compartidos", () => {
    const {container} = render(<CalendarChart location="all" series={[
      {entityId: "one", name: "Ana Pérez", color: "#0077bb"},
      {entityId: "two", name: "A. Pérez", color: "#d55e00"},
    ]} data={[
      {date: "2025-01-02", location: "casa-rosada", record_type: "visitor", records: 1, people: 1, entity_id: "one"},
      {date: "2025-01-02", location: "olivos", record_type: "person", records: 2, people: 1, entity_id: "two"},
    ]} />);

    expect(container.querySelector(".comparison-summary")).toHaveTextContent(/1 día con registros de más de una persona/i);
    const shared = container.querySelector<HTMLElement>(".calendar-day--shared");
    expect(shared?.querySelectorAll(".calendar-day-segment")).toHaveLength(2);
    expect(shared).toHaveAttribute("aria-label", expect.stringContaining("Ana Pérez: 1"));
    fireEvent.pointerEnter(shared!);
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("2 de ene de 2025");
    expect(tooltip).toHaveTextContent("Ana Pérez1");
    expect(tooltip).toHaveTextContent("A. Pérez2");
  });

  it("marca los días de Milei y permite ocultar la capa", () => {
    const {container} = render(<CalendarChart location="casa-rosada" mileiCasaRosadaDays={["2024-01-02"]} data={[
      {date: "2024-01-02", location: "casa-rosada", record_type: "movement", records: 2, people: 1},
    ]} />);

    expect(container.querySelector(".calendar-day--milei")).toBeInTheDocument();
    const checkbox = screen.getByRole("checkbox", {name: /Javier Milei/i});
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(container.querySelector(".calendar-day--milei")).toBeInTheDocument();
  });
});
