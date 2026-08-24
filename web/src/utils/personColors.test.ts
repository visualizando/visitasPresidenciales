import {describe, expect, it} from "vitest";
import type {PersonSummary} from "../types";
import {comparisonSeries} from "./personColors";

function person(entityId: string, name: string): PersonSummary {
  return {entity_id: entityId, canonical_name: name, normalized_name: name, document_type: null, document_number: null, record_count: 1, first_seen: null, last_seen: null, locations: ["olivos"], record_types: ["person"], event_shard: "00"};
}

describe("comparisonSeries", () => {
  it("asigna colores diferentes y nombres legibles a cada selección", () => {
    const result = comparisonSeries([person("one", "PEREZ ANA"), person("two", "ANA PEREZ")]);
    expect(new Set(result.map((item) => item.color))).toHaveLength(2);
    expect(result.map((item) => item.name)).toEqual(["Perez Ana", "Ana Perez"]);
  });
});
