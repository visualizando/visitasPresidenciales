import {useEffect, useRef, useState} from "react";
import type {PersonSummary, SearchFilters} from "../types";

interface State {
  results: PersonSummary[];
  loading: boolean;
  error: string | null;
}

export function useSearch(query: string, filters: SearchFilters): State {
  const workerRef = useRef<Worker | null>(null);
  const requestId = useRef(0);
  const [state, setState] = useState<State>({results: [], loading: false, error: null});

  useEffect(() => {
    const worker = new Worker(new URL("../search.worker.ts", import.meta.url), {type: "module"});
    worker.postMessage({type: "init", baseUrl: new URL("data/", document.baseURI).href});
    workerRef.current = worker;
    worker.onmessage = (event) => {
      if (event.data.type === "results" && event.data.id === requestId.current) {
        setState({results: event.data.results, loading: false, error: null});
      } else if (event.data.type === "error" && event.data.id === requestId.current) {
        setState((current) => ({...current, loading: false, error: event.data.message}));
      }
    };
    return () => worker.terminate();
  }, []);

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < 2) {
      setState({results: [], loading: false, error: null});
      return;
    }
    setState((current) => ({...current, loading: true, error: null}));
    const timeout = window.setTimeout(() => {
      requestId.current += 1;
      workerRef.current?.postMessage({type: "query", id: requestId.current, query: normalized, filters});
    }, 180);
    return () => window.clearTimeout(timeout);
  }, [query, filters]);

  return state;
}

