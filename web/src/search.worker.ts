/// <reference lib="webworker" />

import type {PersonSummary, SearchFilters} from "./types";
import {fetchGzipJson} from "./utils/fetchGzipJson";
import {broadNameShardKeys, exactNameShardKeys} from "./utils/searchShards";

type InitMessage = {type: "init"; baseUrl: string};
type QueryMessage = {type: "query"; id: number; query: string; filters: SearchFilters};
type WorkerMessage = InitMessage | QueryMessage;

let dataBaseUrl = "";
const cache = new Map<string, PersonSummary[]>();
const inflight = new Map<string, Promise<PersonSummary[]>>();
let nameShardKeysPromise: Promise<string[]> | null = null;
let nameFallbackShardKeysPromise: Promise<string[]> | null = null;
let latestRequestId = 0;

self.onmessage = async (event: MessageEvent<WorkerMessage>) => {
  const message = event.data;
  if (message.type === "init") {
    dataBaseUrl = message.baseUrl;
    self.postMessage({type: "ready"});
    return;
  }
  latestRequestId = message.id;
  try {
    const results = await search(message.query, message.filters, message.id);
    if (message.id === latestRequestId) self.postMessage({type: "results", id: message.id, results});
  } catch (error) {
    if (message.id === latestRequestId) {
      self.postMessage({type: "error", id: message.id, message: error instanceof Error ? error.message : "No se pudo buscar"});
    }
  }
};

async function search(query: string, filters: SearchFilters, requestId: number): Promise<PersonSummary[]> {
  const normalized = fold(query);
  if (normalized.length < 2) return [];
  const prepared = {
    value: normalized,
    tokens: normalized.split(" ").filter(Boolean),
    trigrams: trigrams(normalized),
  };
  const digits = query.replace(/\D/g, "");
  const candidates = new Map<string, PersonSummary>();
  if (digits.length >= 3) {
    for (const person of await load(`search/document/${digits.slice(0, 2)}.json.gz`)) {
      candidates.set(person.entity_id, person);
    }
  } else {
    const shardKeys = exactNameShardKeys(prepared.tokens, await nameShardKeys());
    for (const key of shardKeys) {
      for (const person of await load(`search/name/${key}.json.gz`)) {
        candidates.set(person.entity_id, person);
      }
    }
  }
  let results = rank(candidates, prepared, digits, filters);
  if (!digits && (results[0]?.score ?? 0) < 0.82 && prepared.tokens.length && requestId === latestRequestId) {
    self.postMessage({type: "progress", id: requestId, phase: "broadening"});
    const broadKeys = broadNameShardKeys(prepared.tokens, await nameFallbackShardKeys());
    for (const key of broadKeys) {
      for (const person of await load(`search/name-fallback/${key}.json.gz`)) {
        candidates.set(person.entity_id, person);
      }
    }
    results = rank(candidates, prepared, digits, filters);
  }
  return results;
}

function rank(
  candidates: Map<string, PersonSummary>,
  prepared: {value: string; tokens: string[]; trigrams: Set<string>},
  digits: string,
  filters: SearchFilters,
): PersonSummary[] {
  return [...candidates.values()]
    .filter((person) => matchesFilters(person, filters))
    .map((person) => ({...person, score: score(person, prepared, digits)}))
    .filter((person) => (person.score ?? 0) >= 0.34)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || b.record_count - a.record_count)
    .slice(0, 50);
}

async function nameFallbackShardKeys(): Promise<string[]> {
  if (!nameFallbackShardKeysPromise) {
    nameFallbackShardKeysPromise = loadSearchMeta().then((meta) => meta.name_fallback_shards ?? []);
  }
  return nameFallbackShardKeysPromise;
}

async function nameShardKeys(): Promise<string[]> {
  if (!nameShardKeysPromise) {
    nameShardKeysPromise = loadSearchMeta().then((meta) => meta.name_shards ?? []);
  }
  return nameShardKeysPromise;
}

let searchMetaPromise: Promise<{name_shards?: string[]; name_fallback_shards?: string[]}> | null = null;
function loadSearchMeta(): Promise<{name_shards?: string[]; name_fallback_shards?: string[]}> {
  if (!searchMetaPromise) {
    searchMetaPromise = fetch(new URL("search/meta.json", dataBaseUrl)).then((response) => {
      if (!response.ok) throw new Error("No se pudo cargar el índice de búsqueda");
      return response.json();
    });
  }
  return searchMetaPromise;
}

async function load(path: string): Promise<PersonSummary[]> {
  if (cache.has(path)) return cache.get(path)!;
  if (inflight.has(path)) return inflight.get(path)!;
  const request = fetchGzipJson<PersonSummary[]>(new URL(path, dataBaseUrl))
    .catch(() => [])
    .then((people) => {
      cache.set(path, people);
      inflight.delete(path);
      return people;
    });
  inflight.set(path, request);
  return request;
}

function score(
  person: PersonSummary,
  query: {value: string; tokens: string[]; trigrams: Set<string>},
  digits: string,
): number {
  if (digits.length >= 3) {
    if (person.document_number === digits) return 1;
    return person.document_number?.includes(digits) ? 0.82 : 0;
  }
  if (person.normalized_name === query.value) return 1;
  if (person.normalized_name.startsWith(query.value)) return 0.94;
  const nameTokens = person.normalized_name.split(" ");
  const tokenOverlap = query.tokens.filter((token) => nameTokens.some((name) => name.startsWith(token))).length / query.tokens.length;
  return Math.max(tokenOverlap * 0.9, trigramSimilarity(person.normalized_name, query.trigrams));
}

function trigramSimilarity(left: string, right: Set<string>): number {
  const a = trigrams(left);
  const intersection = [...a].filter((item) => right.has(item)).length;
  return a.size + right.size ? (2 * intersection) / (a.size + right.size) : 0;
}

function trigrams(value: string): Set<string> {
  const padded = `  ${value} `;
  return new Set([...Array(Math.max(0, padded.length - 2))].map((_, index) => padded.slice(index, index + 3)));
}

function matchesFilters(person: PersonSummary, filters: SearchFilters): boolean {
  if (filters.location !== "all" && !person.locations.includes(filters.location)) return false;
  if (filters.recordType !== "all" && !person.record_types.includes(filters.recordType)) return false;
  if (filters.year !== "all") {
    const first = person.first_seen ? new Date(person.first_seen).getUTCFullYear() : 0;
    const last = person.last_seen ? new Date(person.last_seen).getUTCFullYear() : 0;
    if (filters.year < first || filters.year > last) return false;
  }
  return true;
}

function fold(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^A-Za-z0-9]+/g, " ").trim().toUpperCase();
}

export {};
