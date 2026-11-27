/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The built app is committed to src/echo_tunes/web/dist (so the wheel and the Docker image
// never need Node) and served by dashboard.py under a strict CSP: no inline scripts or
// styles, so nothing may be inlined into index.html, and fonts must be files (font-src 'self').
const out = fileURLToPath(new URL("../src/echo_tunes/web/dist", import.meta.url));
// `npm run dev` talks to a running echo-tunes dashboard (default: the local test server).
const api = process.env.ECHO_TUNES_DEV_API ?? "http://127.0.0.1:18081";

export default defineConfig({
  base: "./", // relative URLs: the same build works at / (server) and /demo/ (GitHub Pages)
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: out,
    emptyOutDir: true,
    target: "es2022",
    assetsInlineLimit: 0, // no data: URLs (font-src is 'self' only)
    modulePreload: { polyfill: false },
    cssCodeSplit: true,
    sourcemap: false,
    reportCompressedSize: false,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL("./index.html", import.meta.url)),
        login: fileURLToPath(new URL("./login.html", import.meta.url)),
      },
    },
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ["/api", "/manifest.webmanifest", "/static", "/app-icon.png", "/metrics"].map((p) => [
        p,
        { target: api, changeOrigin: false },
      ]),
    ),
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
