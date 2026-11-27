// A static server for the built site (scripts/build_demo.py output) that sends the dashboard's
// real Content-Security-Policy, so the end-to-end test sees exactly what a browser would block.
//   node e2e/serve.mjs <site dir> [port]
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "../site");
const port = Number(process.argv[3] ?? 4173);
// Keep in step with csp() in src/echo_tunes/dashboard.py.
const CSP =
  "default-src 'self'; img-src 'self' https://i.ytimg.com https://lh3.googleusercontent.com " +
  "https://yt3.ggpht.com https://yt3.googleusercontent.com data:; style-src 'self'; " +
  "script-src 'self'; connect-src 'self'; media-src 'self' https://music.example.com; " +
  "frame-ancestors 'none'; base-uri 'none'; form-action 'none'";
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".xml": "application/xml",
  ".txt": "text/plain",
};

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  let path = normalize(join(root, decodeURIComponent(url.pathname)));
  if (!path.startsWith(root)) {
    res.writeHead(403).end();
    return;
  }
  if (existsSync(path) && statSync(path).isDirectory()) path = join(path, "index.html");
  if (!existsSync(path)) {
    res.writeHead(404, { "Content-Security-Policy": CSP }).end("not found");
    return;
  }
  res.writeHead(200, {
    "Content-Type": TYPES[extname(path)] ?? "application/octet-stream",
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
  });
  createReadStream(path).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`serving ${root} on http://127.0.0.1:${port}`));
