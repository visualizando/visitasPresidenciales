/// <reference lib="webworker" />

import type {PersonSummary, SearchFilters} from "./types";
import {fetchGzipJson} from "./utils/fetchGzipJson";

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
    const shardKeys = new Set(normalized.split(" ").filter(Boolean).map((token) => safeShard(token[0])));
    for (const key of shardKeys) {
      for (const person of await load(`search/name/${key}.json.gz`)) {
        candidates.set(person.entity_id, person);
      }
    }
  }
  return [...candidates.values()]
    .filter((person) => matchesFilters(person, filters))
    .map((person) => ({...person, score: score(person, prepared, digits)}))
    .filter((person) => (person.score ?? 0) >= 0.34)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || b.record_count - a.record_count)
    .slice(0, 50);
}

async function load(path: string): Promise<PersonSummary[]> {
  if (cache.has(path)) return cache.get(path)!;
  let people: PersonSummary[];
  try {
    people = await fetchGzipJson<PersonSummary[]>(new URL(path, dataBaseUrl));
  } catch {
    cache.set(path, []);
    return [];
  }
  cache.set(path, people);
  return people;
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

function safeShard(value: string): string {
  const normalized = value.toLowerCase();
  return /^[a-z0-9]$/.test(normalized) ? normalized : "_";
}

export {};
