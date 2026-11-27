// Takes the screenshots scripts/screenshots.py asks for (a JSON list on stdin) with Playwright.
// Each job: { url, out, width, height, scale?, scheme?, mobile?, html? (render this markup) }.
// Uses the installed Chrome when there is one (PW_CHANNEL=chrome, the default), else
// Playwright's Chromium (`npx playwright install chromium`).
import { chromium } from "@playwright/test";

const jobs = JSON.parse(
  await new Promise((resolve) => {
    let data = "";
    process.stdin.on("data", (c) => {
      data += c;
    });
    process.stdin.on("end", () => resolve(data));
  }),
);
const channel = process.env.PW_CHANNEL ?? "chrome";
const browser = await chromium.launch(channel === "chromium" ? {} : { channel });
let failed = false;
for (const job of jobs) {
  const ctx = await browser.newContext({
    viewport: { width: job.width, height: job.height },
    deviceScaleFactor: job.scale ?? 1,
    colorScheme: job.scheme ?? "dark",
    isMobile: !!job.mobile,
    hasTouch: !!job.mobile,
    reducedMotion: "reduce",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().startsWith("Failed to load resource"))
      errors.push(m.text());
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !r.url().endsWith("/favicon.ico"))
      errors.push(`${r.status()} ${r.url()}`);
  });
  if (job.html) await page.setContent(job.html, { waitUntil: "load" });
  else await page.goto(job.url, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(job.wait ?? 1200);
  await page.screenshot({ path: job.out, omitBackground: !!job.transparent });
  if (errors.length) {
    console.error(`${job.out}: ${errors.join("; ")}`);
    failed = true;
  }
  await ctx.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
