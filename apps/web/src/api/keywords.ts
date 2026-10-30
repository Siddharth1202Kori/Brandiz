import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import type { Market } from "../markets";
import { API_BASE, ApiError, api, call } from "./client";
import type { components, operations } from "./schema";

export type KeywordMetrics = components["schemas"]["KeywordMetrics"];
export type SerpSnapshot = components["schemas"]["SerpSnapshot"];
export type Meta = components["schemas"]["Meta"];
export type IdeasMode = "ideas" | "related" | "suggestions";
export type IdeasParams = NonNullable<
  operations["ideas_api_v1_keywords_ideas_get"]["parameters"]["query"]
>;

const DAY = 24 * 60 * 60 * 1000;

export const overviewQuery = (q: string, market: Market) =>
  queryOptions({
    queryKey: ["kw-overview", market, q],
    queryFn: () => call(api.GET("/api/v1/keywords/overview", { params: { query: { q, market } } })),
    staleTime: DAY, // server caches 30 days; no need to refetch within a session
    retry: false,
  });

export const serpQuery = (q: string, market: Market) =>
  queryOptions({
    queryKey: ["kw-serp", market, q],
    queryFn: () => call(api.GET("/api/v1/keywords/serp", { params: { query: { q, market } } })),
    staleTime: 60 * 60 * 1000,
    retry: false,
  });

export const ideasQuery = (params: IdeasParams) =>
  queryOptions({
    queryKey: ["kw-ideas", params],
    queryFn: () => call(api.GET("/api/v1/keywords/ideas", { params: { query: params } })),
    placeholderData: keepPreviousData, // keep the table while paging/sorting
    staleTime: DAY,
    retry: false,
  });

export const listsQuery = queryOptions({
  queryKey: ["kw-lists"],
  queryFn: async () => (await call(api.GET("/api/v1/keywords/lists"))).data,
});

export const listQuery = (id: string) =>
  queryOptions({
    queryKey: ["kw-list", id],
    queryFn: async () =>
      (
        await call(
          api.GET("/api/v1/keywords/lists/{list_id}", { params: { path: { list_id: id } } }),
        )
      ).data,
  });

export const adminUsageQuery = (days: number) =>
  queryOptions({
    queryKey: ["admin-usage", days],
    queryFn: async () =>
      (await call(api.GET("/api/v1/admin/usage", { params: { query: { days } } }))).data,
  });

/** Downloads a CSV export through fetch so quota errors surface as ApiError, not a JSON page. */
export async function downloadCsv(path: string, params: Record<string, unknown>): Promise<void> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    for (const item of Array.isArray(v) ? v : [v]) qs.append(k, String(item));
  }
  const res = await fetch(`${API_BASE}${path}?${qs}`, { credentials: "include" });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    throw new ApiError(
      res.status,
      body.error?.code ?? "http_error",
      body.error?.message ?? res.statusText,
      body.error?.details,
    );
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1];
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name ?? "brandiz-export.csv";
  a.click();
  URL.revokeObjectURL(url);
}
