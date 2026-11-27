// After `vite build`: make the HTML refer to public files relatively (the same build is served
// at / by the dashboard and at /demo/ on GitHub Pages) and check nothing inline slipped in,
// because the dashboard's CSP (script-src 'self'; style-src 'self') would block it.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dist = fileURLToPath(new URL("../../src/echo_tunes/web/dist/", import.meta.url));
let failed = false;
for (const page of ["index.html", "login.html"]) {
  const file = `${dist}${page}`;
  let html = readFileSync(file, "utf8");
  html = html.replaceAll('"/static/', '"./static/');
  writeFileSync(file, html);
  const inlineScript = /<script(?![^>]*\bsrc=)[^>]*>/i.test(html);
  const inlineStyle = /<style[\s>]/i.test(html) || /\sstyle=/i.test(html);
  if (inlineScript || inlineStyle) {
    console.error(`${page}: inline ${inlineScript ? "script" : "style"} (blocked by the CSP)`);
    failed = true;
  }
}
if (failed) process.exit(1);
