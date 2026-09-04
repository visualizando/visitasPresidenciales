import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";
import {ShareButton} from "./ShareButton";

describe("ShareButton", () => {
  it("copia la URL actual al portapapeles", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {value: {writeText}, configurable: true});
    render(<ShareButton />);
    fireEvent.click(screen.getByRole("button", {name: "Compartir"}));
    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(await screen.findByRole("button", {name: "Copiado"})).toBeInTheDocument();
  });
});
