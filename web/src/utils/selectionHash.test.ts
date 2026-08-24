import {describe, expect, it} from "vitest";
import {buildSelectionHash, parseSelectionHash, selectionIdShard} from "./selectionHash";

describe("selectionHash", () => {
  it("serializa y restaura varias personas sin duplicados", () => {
    const hash = buildSelectionHash(["per_ab12", "per_cd34", "per_ab12"]);
    expect(hash).toBe("#person=per_ab12,per_cd34");
    expect(parseSelectionHash(hash)).toEqual(["per_ab12", "per_cd34"]);
  });

  it("distingue los enlaces de selección de las anclas de sección", () => {
    expect(parseSelectionHash("#panorama")).toBeNull();
    expect(parseSelectionHash("#person=../../data,per_ok12")).toEqual(["per_ok12"]);
  });

  it("calcula el mismo shard seguro que el pipeline", () => {
    expect(selectionIdShard("per_ab12")).toBe("12");
    expect(selectionIdShard("per_1")).toBe("_");
  });
});
