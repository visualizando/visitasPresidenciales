/// <reference lib="webworker" />

import type {PersonSummary, SearchFilters} from "./types";

type InitMessage = {type: "init"; baseUrl: string};
type QueryMessage = {type: "query"; id: number; query: string; filters: SearchFilters};
type WorkerMessage = InitMessage | QueryMessage;

let dataBaseUrl = "";
const cache = new Map<string, PersonSummary[]>();

self.onmessage = async (event: MessageEvent<WorkerMessage>) => {
  const message = event.data;
  if (message.type === "init") {
    dataBaseUrl = message.baseUrl;
    self.postMessage({type: "ready"});
    return;
  }
  try {
    const results = await search(message.query, message.filters);
    self.postMessage({type: "results", id: message.id, results});
  } catch (error) {
    self.postMessage({type: "error", id: message.id, message: error instanceof Error ? error.message : "No se pudo buscar"});
  }
};

async function search(query: string, filters: SearchFilters): Promise<PersonSummary[]> {
  const normalized = fold(query);
  if (normalized.length < 2) return [];
  const digits = query.replace(/\D/g, "");
  const candidates = new Map<string, PersonSummary>();
  if (digits.length >= 3) {
    for (const person of await load(`search/document/${digits.slice(0, 2)}.json`)) {
      candidates.set(person.entity_id, person);
    }
  } else {
    const shardKeys = new Set(normalized.split(" ").filter(Boolean).map((token) => safeShard(token[0])));
    for (const key of shardKeys) {
      for (const person of await load(`search/name/${key}.json`)) {
        candidates.set(person.entity_id, person);
      }
    }
  }
  return [...candidates.values()]
    .filter((person) => matchesFilters(person, filters))
    .map((person) => ({...person, score: score(person, normalized, digits)}))
    .filter((person) => (person.score ?? 0) >= 0.34)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || b.record_count - a.record_count)
    .slice(0, 50);
}

async function load(path: string): Promise<PersonSummary[]> {
  if (cache.has(path)) return cache.get(path)!;
  const response = await fetch(new URL(path, dataBaseUrl));
  if (response.status === 404) {
    cache.set(path, []);
    return [];
  }
  if (!response.ok) throw new Error("No se pudo cargar el índice de búsqueda");
  const people = await response.json() as PersonSummary[];
  cache.set(path, people);
  return people;
}

function score(person: PersonSummary, query: string, digits: string): number {
  if (digits.length >= 3) {
    if (person.document_number === digits) return 1;
    return person.document_number?.includes(digits) ? 0.82 : 0;
  }
  if (person.normalized_name === query) return 1;
  if (person.normalized_name.startsWith(query)) return 0.94;
  const queryTokens = new Set(query.split(" "));
  const nameTokens = new Set(person.normalized_name.split(" "));
  const tokenOverlap = [...queryTokens].filter((token) => [...nameTokens].some((name) => name.startsWith(token))).length / queryTokens.size;
  return Math.max(tokenOverlap * 0.9, trigramSimilarity(person.normalized_name, query));
}

function trigramSimilarity(left: string, right: string): number {
  const a = trigrams(left);
  const b = trigrams(right);
  const intersection = [...a].filter((item) => b.has(item)).length;
  return a.size + b.size ? (2 * intersection) / (a.size + b.size) : 0;
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

function safeShard(value: string): string {
  const normalized = value.toLowerCase();
  return /^[a-z0-9]$/.test(normalized) ? normalized : "_";
}

export {};

