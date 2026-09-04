import type {AccessEvent, AudienciaDetail, PersonSummary} from "../types";

export function buildTimelineRows(
  events: AccessEvent[],
  audienciasByEntity: Map<string, AudienciaDetail[]>,
  people: PersonSummary[] = [],
): AccessEvent[] {
  if (!audienciasByEntity.size) return events;

  const peopleById = new Map(people.map((person) => [person.entity_id, person]));
  const rows: AccessEvent[] = [];
  const eventRecordIds = new Set(events.map((event) => event.record_id));
  const fusedByRecordId = new Map<string, AudienciaDetail[]>();
  const standalone: AudienciaDetail[] = [];

  for (const [eid, rowsOfEntity] of audienciasByEntity) {
    for (const audiencia of rowsOfEntity) {
      if (audiencia.status === "confirmed" && audiencia.cr_record_id && eventRecordIds.has(audiencia.cr_record_id)) {
        const list = fusedByRecordId.get(audiencia.cr_record_id) ?? [];
        list.push(audiencia);
        fusedByRecordId.set(audiencia.cr_record_id, list);
      } else {
        standalone.push(audiencia);
      }
    }
  }

  for (const event of events) {
    const fused = event.fused_audiencias?.length ? event.fused_audiencias : fusedByRecordId.get(event.record_id);
    rows.push(fused?.length ? {...event, fused_audiencias: fused} : event);
  }

  for (const audiencia of standalone) {
    rows.push(toAudienciaEvent(audiencia, peopleById));
  }

  return rows;
}

export function toAudienciaEvent(audiencia: AudienciaDetail, peopleById: Map<string, PersonSummary> = new Map()): AccessEvent {
  const person = peopleById.get(audiencia.entity_id);
  return {
    record_id: `aud_${audiencia.audiencia_id}`,
    entity_id: audiencia.entity_id,
    canonical_name: person?.canonical_name ?? audiencia.official_name,
    document_type: person?.document_type ?? null,
    document_number: person?.document_number ?? null,
    location: "casa-rosada",
    record_type: "visitor",
    occurred_at: audiencia.date || null,
    entered_at: null,
    exited_at: null,
    direction: null,
    device: null,
    destination: audiencia.official_name || null,
    purpose: audiencia.lugar || null,
    activity: audiencia.official_cargo || null,
    authorized_by: null,
    access_status: null,
    quality: "medium",
    raw_text: "",
    sources: [],
    audiencia,
  };
}
