import {useEffect, useMemo, useState} from "react";
import type {CoincidenceResult, CoincidenceShard, PersonSummary, RawCoincidenceOwner} from "../types";
import {fetchGzipJson} from "../utils/fetchGzipJson";

type CoincidenceState = {data: CoincidenceResult[]; loading: boolean; error: string | null};

export function useCoincidences(people: PersonSummary[]): CoincidenceState {
  const selectionKey = people.map((person) => person.entity_id).sort().join(",");
  const [state, setState] = useState<CoincidenceState>({data: [], loading: false, error: null});
  const selectedIds = useMemo(() => new Set(people.map((person) => person.entity_id)), [selectionKey]);

  useEffect(() => {
    if (!people.length) {
      setState({data: [], loading: false, error: null});
      return;
    }
    const controller = new AbortController();
    const shards = [...new Set(people.map((person) => person.event_shard))];
    setState({data: [], loading: true, error: null});
    Promise.all(shards.map(async (shard) => {
      return fetchGzipJson<CoincidenceShard>(
        new URL(`data/cooccurrences/${shard}.json.gz`, document.baseURI),
        controller.signal,
      );
    })).then((groups) => {
      const owners = new Map<string, RawCoincidenceOwner>();
      for (const group of groups) for (const person of people) if (group[person.entity_id]) owners.set(person.entity_id, group[person.entity_id]);
      setState({data: aggregateCoincidences(owners, selectedIds), loading: false, error: null});
    }).catch((error: Error) => {
      if (error.name !== "AbortError") setState({data: [], loading: false, error: error.message});
    });
    return () => controller.abort();
  // selectionKey is the stable dependency for the selected identities.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey]);

  return state;
}

export function aggregateCoincidences(owners: Map<string, RawCoincidenceOwner>, selectedIds: Set<string>): CoincidenceResult[] {
  const episodes = new Map<string, {personId: string; name: string; documentType: string | null; documentNumber: string | null; evidence: CoincidenceResult["evidence"][number]}>();
  for (const owner of owners.values()) {
    for (const episode of owner.e) {
      const [personId, date, locationCode, destinationIndex, overlapMinutes, specific, overlapStart, overlapEnd] = episode;
      if (selectedIds.has(personId)) continue;
      const person = owner.p[personId];
      if (!person) continue;
      const destination = owner.d[destinationIndex] ?? "Destino no informado";
      const key = `${personId}|${date}|${locationCode}|${destination}`;
      const current = episodes.get(key);
      if (!current || overlapMinutes > current.evidence.overlapMinutes) episodes.set(key, {
        personId, name: person[0], documentType: person[1], documentNumber: person[2],
        evidence: {date, location: locationCode === 0 ? "casa-rosada" : "olivos", destination, overlapMinutes, specificDestination: specific === 1, overlapStart, overlapEnd},
      });
    }
  }
  const grouped = new Map<string, CoincidenceResult>();
  for (const episode of episodes.values()) {
    const current = grouped.get(episode.personId) ?? {entityId: episode.personId, canonicalName: episode.name, documentType: episode.documentType, documentNumber: episode.documentNumber, days: 0, episodes: 0, overlapMinutes: 0, specificEpisodes: 0, latestDate: "", evidence: []};
    current.evidence.push(episode.evidence);
    current.episodes += 1;
    current.overlapMinutes += episode.evidence.overlapMinutes;
    current.specificEpisodes += Number(episode.evidence.specificDestination);
    if (episode.evidence.date > current.latestDate) current.latestDate = episode.evidence.date;
    grouped.set(episode.personId, current);
  }
  for (const result of grouped.values()) {
    result.days = new Set(result.evidence.map((item) => item.date)).size;
    result.evidence.sort((a, b) => b.date.localeCompare(a.date) || b.overlapMinutes - a.overlapMinutes);
  }
  return [...grouped.values()].sort((a, b) => b.days - a.days || b.specificEpisodes - a.specificEpisodes || b.overlapMinutes - a.overlapMinutes || a.canonicalName.localeCompare(b.canonicalName, "es")).slice(0, 10);
}
