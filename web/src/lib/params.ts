// The page's own ?query (?shots, ?theme=dark for screenshots). boot.js moves it out of the
// address bar before the app starts: the hash router would otherwise read it as part of the
// route's search params (#/search?q=x plus ?shots became q="x?shots").

declare global {
  interface Window {
    etParams?: string;
  }
}

export const pageParams = (): URLSearchParams =>
  new URLSearchParams(typeof window === "undefined" ? "" : (window.etParams ?? location.search));

export const shotsMode = (): boolean => pageParams().has("shots");
