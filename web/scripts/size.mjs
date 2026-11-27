// Size budget for what a phone downloads before the first screen: the JS and CSS that
// index.html loads (entry + its static imports), gzipped. Lazy chunks (Server pages, the demo
// API) don't count. Budget: JS <= 150 KB, CSS <= 25 KB.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const dist = fileURLToPath(new URL("../../src/echo_tunes/web/dist/", import.meta.url));
const BUDGET = { js: 150 * 1024, css: 25 * 1024 };
const html = readFileSync(`${dist}index.html`, "utf8");
const initial = new Set();
const queue = [...html.matchAll(/(?:src|href)="\.?\/?(assets\/[^"]+\.(?:js|css))"/g)].map(
  (m) => m[1],
);
while (queue.length) {
  const file = queue.pop();
  if (initial.has(file)) continue;
  initial.add(file);
  if (file.endsWith(".js")) {
    const code = readFileSync(`${dist}${file}`, "utf8");
    // static imports only: `import ... from "./x.js"` / `import "./x.js"` (not import("..."))
    for (const m of code.matchAll(
      /(?:^|[;\n}])\s*import\s*(?:[^"'(]*?from\s*)?["']\.\/([^"']+\.js)["']/g,
    ))
      queue.push(`assets/${m[1]}`);
  }
}
const gz = (f) => gzipSync(readFileSync(`${dist}${f}`), { level: 9 }).length;
const total = { js: 0, css: 0 };
for (const f of [...initial].sort()) {
  const kind = f.endsWith(".css") ? "css" : "js";
  const size = gz(f);
  total[kind] += size;
  console.log(`${f.padEnd(48)} ${(size / 1024).toFixed(1).padStart(7)} KB gzip`);
}
const all = readdirSync(`${dist}assets`)
  .filter((f) => f.endsWith(".js"))
  .reduce((n, f) => n + statSync(`${dist}assets/${f}`).size, 0);
console.log(
  `initial JS ${(total.js / 1024).toFixed(1)} KB, CSS ${(total.css / 1024).toFixed(1)} KB (gzip); all JS ${(all / 1024).toFixed(0)} KB raw`,
);
let over = false;
for (const k of ["js", "css"]) {
  if (total[k] > BUDGET[k]) {
    console.error(
      `over budget: initial ${k.toUpperCase()} ${(total[k] / 1024).toFixed(1)} KB > ${BUDGET[k] / 1024} KB`,
    );
    over = true;
  }
}
process.exit(over ? 1 : 0);
