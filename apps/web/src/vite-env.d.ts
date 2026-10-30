/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin. Empty = same origin (Vite proxy in dev, Netlify rewrite in prod). */
  readonly VITE_API_URL?: string;
}
