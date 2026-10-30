import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const API_BASE = import.meta.env.VITE_API_URL ?? "";

export const api = createClient<paths>({ baseUrl: API_BASE, credentials: "include" });

function readCookie(name: string): string {
  const hit = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.slice(name.length + 1)) : "";
}

// Double-submit CSRF: echo the readable sm_csrf cookie on every mutating request.
api.use({
  onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      request.headers.set("X-CSRF-Token", readCookie("sm_csrf"));
    }
    return request;
  },
});

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

type ErrorBody = { error?: { code?: string; message?: string; details?: unknown } };

/** Unwraps an openapi-fetch result: returns `data` or throws ApiError with the API's error code. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request;
  if (error !== undefined || !response.ok) {
    const body = (error ?? {}) as ErrorBody;
    throw new ApiError(
      response.status,
      body.error?.code ?? "http_error",
      body.error?.message ?? response.statusText,
      body.error?.details,
    );
  }
  return data as T;
}
