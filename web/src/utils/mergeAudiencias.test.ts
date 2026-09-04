import {describe, expect, it} from "vitest";
import type {AccessEvent, AudienciaDetail} from "../types";
import {buildTimelineRows, toAudienciaEvent} from "./mergeAudiencias";

function event(record_id: string, entity_id: string, occurred_at: string): AccessEvent {
  return {record_id, entity_id, canonical_name: "PEREZ ANA", document_type: "DNI", document_number: "30123456", location: "casa-rosada", record_type: "visitor", occurred_at, entered_at: occurred_at, exited_at: null, direction: null, device: null, destination: "Jefatura", purpose: null, activity: null, authorized_by: null, access_status: null, quality: "high", raw_text: "", sources: []};
}

function audiencia(id: string, status: AudienciaDetail["status"], cr_record_id = ""): AudienciaDetail {
  return {audiencia_id: id, entity_id: "per_a", status, official_name: "MINISTRO X", official_cargo: "Ministro", lugar: "CASA DE GOBIERNO", date: "2024-05-21", cr_destination: "", cr_record_id};
}

describe("mergeAudiencias", () => {
  it("funde audiencias confirmed en la fila CR correspondiente por record_id", () => {
    const events = [event("rec_1", "per_a", "2024-05-21T10:00:00Z")];
    const byEntity = new Map([["per_a", [audiencia("49.435", "confirmed", "rec_1")]]]);
    const rows = buildTimelineRows(events, byEntity);
    expect(rows).toHaveLength(1);
    expect(rows[0].fused_audiencias?.[0].audiencia_id).toBe("49.435");
    expect(rows[0].audiencia).toBeUndefined();
  });

  it("convierte audiencias likely/unconfirmed en filas propias", () => {
    const events: AccessEvent[] = [];
    const byEntity = new Map([["per_a", [audiencia("1", "likely"), audiencia("2", "unconfirmed")]]]);
    const rows = buildTimelineRows(events, byEntity);
    expect(rows).toHaveLength(2);
    expect(rows[0].audiencia?.status).toBe("likely");
    expect(rows[1].audiencia?.status).toBe("unconfirmed");
  });

  it("confirmed sin evento CR cargado se vuelve fila propia", () => {
    const events: AccessEvent[] = [];
    const byEntity = new Map([["per_a", [audiencia("3", "confirmed", "rec_inexistente")]]]);
    const rows = buildTimelineRows(events, byEntity);
    expect(rows).toHaveLength(1);
    expect(rows[0].audiencia?.status).toBe("confirmed");
  });

  it("sin audiencias devuelve los eventos sin cambios", () => {
    const events = [event("rec_1", "per_a", "2024-05-21T10:00:00Z")];
    expect(buildTimelineRows(events, new Map())).toBe(events);
  });

  it("toAudienciaEvent mapea los campos básicos", () => {
    const row = toAudienciaEvent(audiencia("9", "unconfirmed"));
    expect(row.record_id).toBe("aud_9");
    expect(row.location).toBe("casa-rosada");
    expect(row.record_type).toBe("visitor");
    expect(row.occurred_at).toBe("2024-05-21");
    expect(row.sources).toEqual([]);
  });
});
