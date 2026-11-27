import "./styles/app.css";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { StrictMode, useId, useState } from "react";
import { createRoot } from "react-dom/client";
import { applyAccent, applyTheme, watchSystemTheme } from "./lib/theme";

const appName =
  document.querySelector<HTMLMetaElement>('meta[name="application-name"]')?.content || "echo-tunes";

/** Sign in once on this device: the server answers with a long-lived session cookie. */
function SignIn() {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const id = useId();
  return (
    <main className="glow-art relative grid min-h-[100dvh] place-items-center overflow-hidden px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 size-[640px] -translate-x-1/2 rounded-full bg-accent/25 blur-[120px]"
      />
      <form
        className="relative w-full max-w-[400px] rounded-[24px] border border-border bg-elevated/90 p-7 shadow-pop backdrop-blur-xl"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const r = await fetch("/api/login", {
              method: "POST",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ password }),
              credentials: "same-origin",
            });
            if (r.ok) {
              location.replace("/#/");
              return;
            }
            const data = (await r.json().catch(() => ({}))) as { detail?: unknown };
            setError(
              typeof data.detail === "string" ? data.detail : `Couldn't sign in (${r.status}).`,
            );
          } catch {
            setError("Can't reach echo-tunes.");
          }
          setBusy(false);
        }}
      >
        <div className="flex items-center gap-3">
          <img
            src="static/icon.svg"
            alt=""
            width={44}
            height={44}
            className="size-11 rounded-[12px]"
          />
          <span className="text-[20px] font-bold tracking-tight">{appName}</span>
        </div>
        <h1 className="mt-6 text-[26px] font-extrabold tracking-[-0.02em]">Sign in</h1>
        <p className="mt-1 text-[14px] text-fg-muted">
          Once on this device, and it stays signed in.
        </p>
        <input type="text" name="username" value="admin" autoComplete="username" readOnly hidden />
        <label htmlFor={id} className="mt-6 block text-[13px] font-semibold text-fg-muted">
          Password
        </label>
        <div className="relative mt-1.5">
          <input
            id={id}
            name="password"
            type={show ? "text" : "password"}
            autoComplete="current-password"
            required
            // biome-ignore lint/a11y/noAutofocus: the only field on the page
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!error}
            aria-describedby={error ? `${id}-error` : undefined}
            className="h-12 w-full rounded-[12px] border border-border bg-surface pr-12 pl-4 text-[16px] text-fg focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? "Hide password" : "Show password"}
            className="absolute top-1/2 right-1 grid size-10 -translate-y-1/2 place-items-center rounded-full text-fg-muted hover:bg-surface-2"
          >
            {show ? <EyeOff className="size-5" /> : <Eye className="size-5" />}
          </button>
        </div>
        {error && (
          <p id={`${id}-error`} role="alert" className="mt-3 text-[14px] font-medium text-danger">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="mt-6 inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-accent text-[15px] font-bold text-accent-fg transition-[filter,scale] hover:brightness-110 active:scale-[0.98] disabled:opacity-60"
        >
          {busy && <LoaderCircle className="size-5 animate-spin" aria-hidden />}
          Sign in
        </button>
        <p className="mt-5 text-[13px] text-fg-muted">
          The password is{" "}
          <code className="rounded bg-surface-2 px-1.5 py-0.5 text-fg">
            ECHO_TUNES_DASHBOARD_PASSWORD
          </code>{" "}
          on your server.
        </p>
      </form>
    </main>
  );
}

applyTheme();
watchSystemTheme();
applyAccent();
if ("serviceWorker" in navigator && window.isSecureContext)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
const el = document.getElementById("root");
if (el)
  createRoot(el).render(
    <StrictMode>
      <SignIn />
    </StrictMode>,
  );
