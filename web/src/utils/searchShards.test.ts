import {describe, expect, it} from "vitest";
import {broadNameShardKeys, exactNameShardKeys} from "./searchShards";

const shards = ["mar", "mas", "mat", "per", "pez"];

describe("searchShards", () => {
  it("usa sólo las primeras tres letras cuando están disponibles", () => {
    expect([...exactNameShardKeys(["MARTINEZ"], shards)]).toEqual(["mar"]);
  });

  it("expande consultas de dos letras sin volver a la inicial completa", () => {
    expect([...exactNameShardKeys(["MA"], shards)]).toEqual(["mar", "mas", "mat"]);
  });

  it("ofrece una segunda pasada por inicial para errores tempranos", () => {
    expect([...broadNameShardKeys(["MRA"], ["m", "p"])]).toEqual(["m"]);
  });
});
