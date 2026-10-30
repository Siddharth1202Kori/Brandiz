import type { QueryClient } from "@tanstack/react-query";
import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";

import type { IdeasMode, IdeasParams } from "./api/keywords";
import { meQuery } from "./api/queries";
import { AppLayout } from "./components/AppLayout";
import { WakeBanner } from "./components/WakeBanner";
import type { Market } from "./markets";
import { AdminUsagePage } from "./pages/AdminUsagePage";
import { DashboardPage } from "./pages/DashboardPage";
import { KeywordMagicPage } from "./pages/keywords/KeywordMagicPage";
import { KeywordOverviewPage } from "./pages/keywords/KeywordOverviewPage";
import { ListDetailPage } from "./pages/keywords/ListDetailPage";
import { ListsPage } from "./pages/keywords/ListsPage";
import { LoginPage } from "./pages/LoginPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SignupPage } from "./pages/SignupPage";
import { VerifyPage } from "./pages/VerifyPage";

type Ctx = { queryClient: QueryClient };
type Raw = Record<string, unknown>;

// -- URL search param parsing (URLs stay shareable: every filter lives in the query string) --
const str = (v: unknown) => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v: unknown) => {
  const n = typeof v === "number" ? v : typeof v === "string" && v !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : undefined;
};
const list = (v: unknown) => {
  const items = (Array.isArray(v) ? v : v === undefined ? [] : [v]).map(str).filter(Boolean);
  return items.length ? items : undefined;
};
const market = (v: unknown): Market | undefined => (v === "in" || v === "us" ? v : undefined);
const oneOf = <T extends string>(v: unknown, values: readonly T[]) =>
  values.includes(v as T) ? (v as T) : undefined;

const SORTS = ["keyword", "volume", "kd", "cpc", "competition"] as const;
const MODES: readonly IdeasMode[] = ["ideas", "related", "suggestions"];

export type MagicSearch = {
  seed: string;
  market?: Market;
  mode?: IdeasMode;
  sort?: NonNullable<IdeasParams["sort"]>;
  dir?: "asc" | "desc";
  page?: number;
  volume_min?: number;
  volume_max?: number;
  kd_min?: number;
  kd_max?: number;
  cpc_min?: number;
  cpc_max?: number;
  words_min?: number;
  words_max?: number;
  intent?: string[];
  include?: string[];
  exclude?: string[];
};

const rootRoute = createRootRouteWithContext<Ctx>()({
  component: () => (
    <>
      <WakeBanner />
      <Outlet />
    </>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/dashboard" });
  },
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (s: Record<string, unknown>) => ({
    error: typeof s.error === "string" ? s.error : undefined,
  }),
  component: LoginPage,
});

const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  component: SignupPage,
});

const verifyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/verify",
  validateSearch: (s: Record<string, unknown>) => ({
    token: typeof s.token === "string" ? s.token : "",
  }),
  component: VerifyPage,
});

// Auth guard: everything under this layout requires a session.
const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: async ({ context }) => {
    try {
      await context.queryClient.ensureQueryData(meQuery);
    } catch {
      throw redirect({ to: "/login", search: { error: undefined } });
    }
  },
  component: AppLayout,
});

const dashboardRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/dashboard",
  component: DashboardPage,
});

const projectsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects",
  component: ProjectsPage,
});

const keywordOverviewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/keywords/overview",
  validateSearch: (s: Raw): { q: string; market?: Market } => ({
    q: str(s.q),
    market: market(s.market),
  }),
  component: KeywordOverviewPage,
});

const keywordMagicRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/keywords/magic",
  validateSearch: (s: Raw): MagicSearch => ({
    seed: str(s.seed),
    market: market(s.market),
    mode: oneOf(s.mode, MODES),
    sort: oneOf(s.sort, SORTS),
    dir: oneOf(s.dir, ["asc", "desc"] as const),
    page: num(s.page),
    volume_min: num(s.volume_min),
    volume_max: num(s.volume_max),
    kd_min: num(s.kd_min),
    kd_max: num(s.kd_max),
    cpc_min: num(s.cpc_min),
    cpc_max: num(s.cpc_max),
    words_min: num(s.words_min),
    words_max: num(s.words_max),
    intent: list(s.intent),
    include: list(s.include),
    exclude: list(s.exclude),
  }),
  component: KeywordMagicPage,
});

const listsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/keywords/lists",
  component: ListsPage,
});

const listDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/keywords/lists/$listId",
  component: ListDetailPage,
});

const adminUsageRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/usage",
  component: AdminUsagePage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  signupRoute,
  verifyRoute,
  appRoute.addChildren([
    dashboardRoute,
    projectsRoute,
    keywordOverviewRoute,
    keywordMagicRoute,
    listsRoute,
    listDetailRoute,
    adminUsageRoute,
  ]),
]);

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
