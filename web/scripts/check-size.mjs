import {readdir, stat} from "node:fs/promises";
import {join, relative} from "node:path";
import {gzipSync} from "node:zlib";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";

const root = fileURLToPath(new URL("../dist/", import.meta.url));
const limits = {app: 500 * 1024, shard: 3 * 1024 * 1024, analytics: 1024 * 1024, total: 750 * 1024 * 1024};
let total = 0;
let appCompressed = 0;

async function walk(directory) {
  for (const name of await readdir(directory)) {
    const path = join(directory, name);
    const info = await stat(path);
    if (info.isDirectory()) await walk(path);
    else {
      total += info.size;
      const rel = relative(root, path).replaceAll("\\", "/");
      if (/^assets\/.*\.(js|css)$/.test(rel)) appCompressed += gzipSync(await readFile(path)).length;
      if ((rel.includes("/search/") || rel.includes("/events/")) && info.size > limits.shard) throw new Error(`${rel} supera 3 MB`);
      if (rel.includes("/analytics/") && info.size > limits.analytics) throw new Error(`${rel} supera 1 MB`);
    }
  }
}

await walk(root);
if (appCompressed > limits.app) throw new Error(`La aplicación comprimida pesa ${appCompressed} bytes; máximo ${limits.app}`);
if (total > limits.total) throw new Error(`El sitio pesa ${total} bytes; máximo ${limits.total}`);
console.log(`Presupuesto OK: app ${Math.round(appCompressed / 1024)} KiB gzip, sitio ${Math.round(total / 1024)} KiB`);
