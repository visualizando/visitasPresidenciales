import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {ChartLocationFilter} from "./ChartLocationFilter";

describe("ChartLocationFilter", () => {
  it("permite una o ambas sedes, pero nunca ninguna", () => {
    const onChange = vi.fn();
    const {rerender} = render(<ChartLocationFilter value={["casa-rosada", "olivos"]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("checkbox", {name: "Casa Rosada"}));
    expect(onChange).toHaveBeenLastCalledWith(["olivos"]);

    rerender(<ChartLocationFilter value={["olivos"]} onChange={onChange} />);
    expect(screen.getByRole("checkbox", {name: "Olivos"})).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", {name: "Casa Rosada"}));
    expect(onChange).toHaveBeenLastCalledWith(["olivos", "casa-rosada"]);
  });
});
