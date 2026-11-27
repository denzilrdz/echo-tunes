// Runs before the page paints (a file, not inline: the CSP allows no inline scripts). Applies
// the saved theme and the server's accent colour so the first frame already looks right, and
// moves old bookmarks (#play, #now, ...) to the new pages.
(() => {
  const root = document.documentElement;
  let theme = "system";
  try {
    theme = localStorage.getItem("et.theme") || "system";
  } catch {}
  // ?shots, ?theme=: kept for the app (window.etParams), then taken out of the address so
  // the hash router doesn't mistake them for its own search params.
  window.etParams = location.search;
  const params = new URLSearchParams(location.search);
  if (location.search) history.replaceState(null, "", location.pathname + location.hash);
  const forced = params.get("theme");
  if (forced === "light" || forced === "dark") theme = forced;
  const dark =
    theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  root.dataset.theme = dark ? "dark" : "light";
  root.style.colorScheme = dark ? "dark" : "light";
  if (theme !== "system") {
    for (const m of document.querySelectorAll('meta[name="theme-color"]')) {
      m.setAttribute("content", dark ? "#0B0B0F" : "#FAFAFB");
    }
  }
  const old = {
    "#play": "#/",
    "#now": "#/devices",
    "#history": "#/server/history",
    "#stats": "#/server/stats",
    "#monitor": "#/server/status",
    "#setup": "#/server/setup",
  };
  if (old[location.hash]) history.replaceState(null, "", old[location.hash]);
})();
