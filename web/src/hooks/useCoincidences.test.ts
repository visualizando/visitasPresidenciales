import {describe, expect, it} from "vitest";
import type {RawCoincidenceOwner} from "../types";
import {aggregateCoincidences} from "./useCoincidences";

describe("aggregateCoincidences", () => {
  it("une variantes, evita duplicados y ordena por días coincidentes", () => {
    const first: RawCoincidenceOwner = {d: ["Despacho"], p: {other: ["OTRA PERSONA", "DNI", "123"]}, e: [["other", "2024-01-01", 0, 0, 30, 1, "09:30", "10:00"], ["other", "2024-01-02", 0, 0, 20, 1, "10:00", "10:20"]]};
    const alias: RawCoincidenceOwner = {d: ["Despacho"], p: {other: ["OTRA PERSONA", "DNI", "123"]}, e: [["other", "2024-01-01", 0, 0, 15, 1, "09:45", "10:00"]]};
    const result = aggregateCoincidences(new Map([["selected", first], ["alias", alias]]), new Set(["selected", "alias"]));
    expect(result[0]).toMatchObject({entityId: "other", days: 2, episodes: 2, overlapMinutes: 50, specificEpisodes: 2});
  });
});
