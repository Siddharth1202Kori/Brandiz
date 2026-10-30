import { queryOptions } from "@tanstack/react-query";

import { API_BASE, api, call } from "./client";

export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: async () => (await call(api.GET("/api/v1/auth/me"))).data,
  retry: false,
  staleTime: 60_000,
});

export const limitsQuery = queryOptions({
  queryKey: ["limits"],
  queryFn: async () => (await call(api.GET("/api/v1/limits/me"))).data,
});

export const projectsQuery = queryOptions({
  queryKey: ["projects"],
  queryFn: async () => (await call(api.GET("/api/v1/projects"))).data,
});

/** Free-tier API host sleeps when idle; this ping doubles as the wake-up call. */
export const healthQuery = queryOptions({
  queryKey: ["healthz"],
  queryFn: async () => {
    const res = await fetch(`${API_BASE}/healthz`);
    if (!res.ok) throw new Error(`healthz ${res.status}`);
    return (await res.json()) as { status: string };
  },
  retry: 20,
  retryDelay: 3000,
  staleTime: Infinity,
});
