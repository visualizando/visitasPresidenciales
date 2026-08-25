import {fireEvent, render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import type {CoincidenceResult} from "../types";
import {CoincidenceRanking} from "./CoincidenceRanking";

const result: CoincidenceResult = {
  entityId: "person-2", canonicalName: "PEREZ ANA", documentType: "DNI", documentNumber: "30123456",
  days: 2, episodes: 2, overlapMinutes: 95, specificEpisodes: 2, latestDate: "2024-05-24",
  evidence: [{date: "2024-05-24", location: "casa-rosada", destination: "Jefatura", overlapMinutes: 50, overlapStart: "10:00", overlapEnd: "10:50", specificDestination: true}],
};

describe("CoincidenceRanking", () => {
  it("muestra el total y permanece cerrado hasta que se despliega", () => {
    const {container} = render(<CoincidenceRanking results={[result, {...result, entityId: "person-3", canonicalName: "GOMEZ LUIS"}]} />);
    const disclosure = container.querySelector(".coincidence-disclosure");
    expect(screen.getByRole("heading", {name: "Coincidencias precisas: 2"})).toBeInTheDocument();
    expect(disclosure).not.toHaveAttribute("open");
    expect(screen.getByText("Perez Ana")).not.toBeVisible();
    fireEvent.click(screen.getByText("Coincidencias precisas: 2"));
    expect(disclosure).toHaveAttribute("open");
    expect(screen.getByText("Perez Ana")).toBeVisible();
  });
});
