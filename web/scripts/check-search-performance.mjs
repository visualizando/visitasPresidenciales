import {readdir, readFile, stat} from "node:fs/promises";
import {join} from "node:path";
import {fileURLToPath} from "node:url";
import {performance} from "node:perf_hooks";
import {gunzipSync} from "node:zlib";

const shards = fileURLToPath(new URL("../dist/data/search/name/", import.meta.url));
const files = await readdir(shards);
const sizes = await Promise.all(files.map(async (name) => ({name, size: (await stat(join(shards, name))).size})));
const largest = sizes.sort((left, right) => right.size - left.size)[0];
const people = JSON.parse(gunzipSync(await readFile(join(shards, largest.name))).toString("utf8"));
const query = people[0]?.normalized_name?.split(" ")[0] ?? "PEREZ";
const queryTokens = query.split(" ").filter(Boolean);
const queryTrigrams = trigrams(query);
const timings = [];

for (let iteration = 0; iteration < 25; iteration += 1) {
  const start = performance.now();
  people
    .map((person) => ({person, score: score(person.normalized_name, query, queryTokens, queryTrigrams)}))
    .filter(({score}) => score >= 0.34)
    .sort((left, right) => right.score - left.score || right.person.record_count - left.person.record_count)
    .slice(0, 50);
  timings.push(performance.now() - start);
}

timings.sort((left, right) => left - right);
const p95 = timings[Math.floor(timings.length * 0.95)];
if (p95 >= 100) throw new Error(`La búsqueda caliente p95 tardó ${p95.toFixed(1)} ms; máximo 100 ms`);
console.log(`Búsqueda caliente OK: p95 ${p95.toFixed(1)} ms sobre ${people.length} personas`);

function score(name, query, queryTokens, queryTrigrams) {
  if (name === query) return 1;
  if (name.startsWith(query)) return 0.94;
  const nameTokens = name.split(" ");
  const overlap = queryTokens.filter((token) => nameTokens.some((nameToken) => nameToken.startsWith(token))).length / queryTokens.length;
  return Math.max(overlap * 0.9, trigramSimilarity(name, queryTrigrams));
}

function trigramSimilarity(left, right) {
  const a = trigrams(left);
  const intersection = [...a].filter((item) => right.has(item)).length;
  return a.size + right.size ? (2 * intersection) / (a.size + right.size) : 0;
}

function trigrams(value) {
  const padded = `  ${value} `;
  return new Set([...Array(Math.max(0, padded.length - 2))].map((_, index) => padded.slice(index, index + 3)));
}
