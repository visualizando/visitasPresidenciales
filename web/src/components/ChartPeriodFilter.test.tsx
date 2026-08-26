import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {ChartPeriodFilter} from "./ChartPeriodFilter";

describe("ChartPeriodFilter", () => {
  it("permite alternar entre todo y la presidencia actual", () => {
    const onChange = vi.fn();
    render(<ChartPeriodFilter value="all" onChange={onChange} />);
    expect(screen.getByRole("button", {name: "Todo"})).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", {name: "Presidencia actual"}));
    expect(onChange).toHaveBeenCalledWith("current-presidency");
  });
});
