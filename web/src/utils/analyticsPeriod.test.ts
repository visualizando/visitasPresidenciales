import {describe, expect, it} from "vitest";
import type {AccessEvent, Analytics} from "../types";
import {analyticsForChartPeriod, eventsForChartPeriod} from "./analyticsPeriod";

const analytics: Analytics = {
  daily: [
    {date: "2022-12-31", location: "olivos", record_type: "person", records: 2, people: 2},
    {date: "2023-01-01", location: "olivos", record_type: "person", records: 3, people: 3},
  ],
  monthly: [
    {month: "2022-12", location: "olivos", records: 2, people: 2},
    {month: "2023-01", location: "olivos", records: 3, people: 3},
  ],
  heatmap: [{location: "olivos", weekday: 1, hour: 9, records: 5}],
  purposes: [{location: "olivos", label: "RPO", records: 5}],
  current_presidency: {
    start_date: "2023-01-01",
    heatmap: [{location: "olivos", weekday: 1, hour: 9, records: 3}],
    purposes: [{location: "olivos", label: "RPO", records: 3}],
  },
  coverage: {first_date: "2022-12-31", last_date: "2023-01-01"},
};

function event(recordId: string, occurredAt: string | null): AccessEvent {
  return {record_id: recordId, entity_id: "one", canonical_name: "PEREZ ANA", document_type: null, document_number: null, location: "olivos", record_type: "person", occurred_at: occurredAt, entered_at: null, exited_at: null, direction: null, device: null, destination: null, purpose: null, activity: null, authorized_by: null, access_status: null, quality: "high", raw_text: "", sources: []};
}

describe("analyticsPeriod", () => {
  it("filtra todos los datasets publicados desde 2023", () => {
    const filtered = analyticsForChartPeriod(analytics, "current-presidency");
    expect(filtered?.daily.map((point) => point.date)).toEqual(["2023-01-01"]);
    expect(filtered?.monthly.map((point) => point.month)).toEqual(["2023-01"]);
    expect(filtered?.heatmap[0].records).toBe(3);
    expect(filtered?.purposes[0].records).toBe(3);
  });

  it("filtra los eventos seleccionados antes de agregarlos", () => {
    expect(eventsForChartPeriod([event("old", "2022-12-31T09:00:00Z"), event("current", "2023-01-01T09:00:00Z"), event("undated", null)], "current-presidency").map((item) => item.record_id)).toEqual(["current"]);
  });
});
