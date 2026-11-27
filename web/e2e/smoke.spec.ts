import { expect, type Page, test } from "@playwright/test";

const DEMO = "http://127.0.0.1:4173/demo/";
const DASHBOARD = "http://127.0.0.1:4174";

/** Fails the test on any CSP violation, uncaught error or console error. */
async function watch(page: Page, allow: RegExp[] = []) {
  const problems: string[] = [];
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) =>
      console.error(`CSP violation: ${e.violatedDirective} ${e.blockedURI}`),
    );
  });
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !allow.some((r) => r.test(m.text()))) problems.push(m.text());
  });
  return problems;
}

const noSideScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

const PAGES = [
  "#/",
  "#/search?q=neon",
  "#/search?q=neon&type=album",
  "#/library",
  "#/devices",
  "#/collection/playlist/playlist-Focus-Flow",
  "#/mood/demo-Chill?title=Chill",
  "#/server",
  "#/server/status",
  "#/server/stats",
  "#/server/history",
  "#/server/setup",
  "#/server/settings",
];

test("every page of the demo renders under the CSP, without sideways scrolling", async ({
  page,
}) => {
  const problems = await watch(page);
  await page.goto(`${DEMO}?shots`);
  for (const hash of PAGES) {
    await page.goto(`${DEMO}${hash}`);
    await expect(page.locator("main :is(h1, h2):visible").first()).toBeVisible();
    await page.waitForTimeout(300);
    expect(await noSideScroll(page), hash).toBeLessThanOrEqual(0);
  }
  for (const theme of ["light", "dark"]) {
    await page.goto(`${DEMO}?shots&theme=${theme}&sheet=now`);
    await expect(page.getByRole("dialog", { name: "Now playing" })).toBeVisible();
  }
  expect(problems).toEqual([]);
});

test("first run: pick a favourite Echo, queue a song on it, play here instead", async ({
  page,
}) => {
  const problems = await watch(page);
  await page.goto(DEMO);
  const welcome = page.getByRole("dialog", { name: "Where should music play?" });
  await expect(welcome).toBeVisible();
  await welcome.getByRole("button", { name: /^Living room/ }).click();
  await page.getByRole("button", { name: "Got it" }).click(); // one-time Echo note
  expect(await page.evaluate(() => localStorage.getItem("et.favourite"))).toBe('"DEMO0LIVING1"');

  await page
    .getByRole("button", { name: /^More for / })
    .first()
    .click();
  await page.getByRole("menuitem", { name: "Play next on Living room" }).click();
  await expect(page.getByRole("status")).toContainText("queued on Living room");

  // An idle Echo can't be started from a web page: say so, and offer this browser instead.
  await page.reload();
  await page
    .getByRole("button", { name: /Choose (a device|where music plays)/ })
    .first()
    .click();
  await page
    .getByRole("dialog", { name: "Play on" })
    .getByRole("button", { name: /^Bedroom/ })
    .click();
  await page
    .getByRole("button", { name: /^More for / })
    .first()
    .click();
  await page.getByRole("menuitem", { name: /^Play next on Bedroom/ }).click();
  await page.getByRole("button", { name: "Play here instead" }).click();
  await expect(page.getByRole("button", { name: /^(Pause|Play)$/ }).first()).toBeVisible();
  expect(problems).toEqual([]);
});

test("the real dashboard: sign in, browse without YouTube, sign out", async ({ page }) => {
  // Without a catalog the browse API answers 404: the page shows that, nothing breaks.
  const problems = await watch(page, [/Failed to load resource/]);
  await page.goto(`${DASHBOARD}/`);
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole("textbox", { name: "Password" }).fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Wrong password");
  await page.getByRole("textbox", { name: "Password" }).fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/#\//);
  await expect(page.getByRole("dialog", { name: "Where should music play?" })).toBeVisible();
  await page.keyboard.press("Escape");
  for (const hash of ["#/server/status", "#/server/history", "#/server/settings"]) {
    await page.goto(`${DASHBOARD}/${hash}`);
    await expect(page.locator("main h1:visible").first()).toBeVisible();
  }
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(problems).toEqual([]);
});

test("an unreachable server gets an explanation that clears once it answers", async ({ page }) => {
  // e.g. a phone's own "Private DNS" resolving the dashboard to an address that doesn't serve it
  const problems = await watch(page, [/Failed to load resource/, /ERR_FAILED/]);
  await page.goto(`${DASHBOARD}/login`);
  await page.getByRole("textbox", { name: "Password" }).fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/#\//);
  await page.keyboard.press("Escape"); // the first-run question

  await page.route("**/api/**", (route) => route.abort("connectionrefused"));
  await page.goto(`${DASHBOARD}/#/server/status`);
  const screen = page.getByRole("alert").filter({ hasText: "Can't reach your echo-tunes server" });
  await expect(screen).toBeVisible({ timeout: 15_000 });
  await expect(screen).toContainText("127.0.0.1:4174");
  await screen.getByText("Why might this happen?").click();
  await expect(screen).toContainText("Private DNS");
  await expect(page.getByRole("button", { name: "Try again" })).toBeEnabled();

  await page.unroute("**/api/**");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(screen).toBeHidden();
  expect(problems).toEqual([]);
});
