import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {ChartLocationFilter} from "./ChartLocationFilter";

describe("ChartLocationFilter", () => {
  it("permite elegir Casa Rosada, Olivos o ambas sedes", () => {
    const onChange = vi.fn();
    const {rerender} = render(<ChartLocationFilter value={["casa-rosada", "olivos"]} onChange={onChange} />);
    expect(screen.getByRole("radio", {name: "Casa Rosada y Olivos"})).toBeChecked();
    fireEvent.click(screen.getByRole("radio", {name: "Solo Casa Rosada"}));
    expect(onChange).toHaveBeenLastCalledWith(["casa-rosada"]);

    rerender(<ChartLocationFilter value={["olivos"]} onChange={onChange} />);
    expect(screen.getByRole("radio", {name: "Solo Olivos"})).toBeChecked();
    fireEvent.click(screen.getByRole("radio", {name: "Casa Rosada y Olivos"}));
    expect(onChange).toHaveBeenLastCalledWith(["casa-rosada", "olivos"]);
  });
});
