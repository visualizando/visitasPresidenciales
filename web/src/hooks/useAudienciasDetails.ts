import {useEffect, useMemo, useState} from "react";
import type {AudienciaDetail, PersonSummary} from "../types";
import {fetchGzipJson} from "../utils/fetchGzipJson";

type AudienciasShard = Record<string, AudienciaDetail[]>;

export type AudienciasDetailsState = {
  details: Map<string, AudienciaDetail[]>;
  loading: boolean;
  error: string | null;
};

export function useAudienciasDetails(people: PersonSummary[]): AudienciasDetailsState {
  const selectionKey = people.map((person) => person.entity_id).sort().join(",");
  const selectedIds = useMemo(() => new Set(people.map((person) => person.entity_id)), [selectionKey]);
  const [state, setState] = useState<AudienciasDetailsState>({details: new Map(), loading: false, error: null});

  useEffect(() => {
    if (!people.length) {
      setState({details: new Map(), loading: false, error: null});
      return;
    }
    const controller = new AbortController();
    const shards = [...new Set(people.map((person) => person.event_shard))];
    setState((current) => ({details: current.details, loading: true, error: null}));
    Promise.all(shards.map(async (shard) => {
      return fetchGzipJson<AudienciasShard>(
        new URL(`data/audiencias/${shard}.json.gz`, document.baseURI),
        controller.signal,
      );
    })).then((groups) => {
      const merged = new Map<string, AudienciaDetail[]>();
      for (const group of groups) {
        for (const [eid, rows] of Object.entries(group)) {
          if (selectedIds.has(eid)) merged.set(eid, rows);
        }
      }
      setState({details: merged, loading: false, error: null});
    }).catch((error: Error) => {
      if (error.name !== "AbortError") setState({details: new Map(), loading: false, error: error.message});
    });
    return () => controller.abort();
  // selectionKey is the stable dependency for the selected identities.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey]);

  return state;
}
