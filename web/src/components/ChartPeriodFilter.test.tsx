import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {ChartPeriodFilter} from "./ChartPeriodFilter";

describe("ChartPeriodFilter", () => {
  it("permite alternar entre todo y la presidencia actual", () => {
    const onChange = vi.fn();
    render(<ChartPeriodFilter value="all" onChange={onChange} />);
    const toggle = screen.getByRole("checkbox", {name: "Mostrar solo la presidencia actual"});
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith("current-presidency");
  });
});
