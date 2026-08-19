import {readdir, readFile, stat} from "node:fs/promises";
import {join} from "node:path";
import {fileURLToPath} from "node:url";
import {performance} from "node:perf_hooks";

const shards = fileURLToPath(new URL("../dist/data/search/name/", import.meta.url));
const files = await readdir(shards);
const sizes = await Promise.all(files.map(async (name) => ({name, size: (await stat(join(shards, name))).size})));
const largest = sizes.sort((left, right) => right.size - left.size)[0];
const people = JSON.parse(await readFile(join(shards, largest.name), "utf8"));
const query = people[0]?.normalized_name?.split(" ")[0] ?? "PEREZ";
const timings = [];

for (let iteration = 0; iteration < 25; iteration += 1) {
  const start = performance.now();
  people
    .map((person) => ({person, score: score(person.normalized_name, query)}))
    .filter(({score}) => score >= 0.34)
    .sort((left, right) => right.score - left.score || right.person.record_count - left.person.record_count)
    .slice(0, 50);
  timings.push(performance.now() - start);
}

timings.sort((left, right) => left - right);
const p95 = timings[Math.floor(timings.length * 0.95)];
if (p95 >= 100) throw new Error(`La búsqueda caliente p95 tardó ${p95.toFixed(1)} ms; máximo 100 ms`);
console.log(`Búsqueda caliente OK: p95 ${p95.toFixed(1)} ms sobre ${people.length} personas`);

function score(name, query) {
  if (name === query) return 1;
  if (name.startsWith(query)) return 0.94;
  const queryTokens = new Set(query.split(" "));
  const nameTokens = new Set(name.split(" "));
  const overlap = [...queryTokens].filter((token) => [...nameTokens].some((nameToken) => nameToken.startsWith(token))).length / queryTokens.size;
  return Math.max(overlap * 0.9, trigramSimilarity(name, query));
}

function trigramSimilarity(left, right) {
  const a = trigrams(left);
  const b = trigrams(right);
  const intersection = [...a].filter((item) => b.has(item)).length;
  return a.size + b.size ? (2 * intersection) / (a.size + b.size) : 0;
}

function trigrams(value) {
  const padded = `  ${value} `;
  return new Set([...Array(Math.max(0, padded.length - 2))].map((_, index) => padded.slice(index, index + 3)));
}
