import "./styles/app.css";
import { CSPProvider } from "@base-ui/react/csp-provider";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { queryClient } from "./lib/queries";
import { applyAccent, applyTheme, watchSystemTheme } from "./lib/theme";
import { router } from "./router";

async function start(): Promise<void> {
  applyTheme();
  watchSystemTheme();
  applyAccent();
  // The GitHub Pages demo: build_demo.py adds this meta tag, and the fake API (its own chunk,
  // never loaded on a real server) answers every call.
  if (document.querySelector('meta[name="echo-tunes-demo"]')) {
    const demo = await import("./demo/demo-api");
    demo.install();
  } else if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch((err) => console.warn("service worker:", err));
  }
  const el = document.getElementById("root");
  if (!el) return;
  createRoot(el).render(
    <StrictMode>
      {/* Base UI must not inject <style> elements: the CSP allows only our stylesheet. */}
      <CSPProvider disableStyleElements>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </CSPProvider>
    </StrictMode>,
  );
}

void start();
