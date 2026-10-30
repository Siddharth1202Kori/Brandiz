import Button from "@semcore/ui/button";
import Select from "@semcore/ui/select";
import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, Outlet, useNavigate } from "@tanstack/react-router";

import { api, call } from "../api/client";
import { meQuery } from "../api/queries";
import { MARKET_OPTIONS, type Market } from "../markets";
import { KeywordSearch } from "./KeywordSearch";

// Tools arrive phase by phase (see Phases/README.md).
const SOON = [
  ["Domain Overview", "P2"],
  ["Backlinks", "P3"],
  ["Search Console", "P4"],
  ["Rank Tracking", "P5"],
  ["Site Audit", "P6"],
] as const;

export function AppLayout() {
  const { data: me } = useSuspenseQuery(meQuery);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const setMarket = useMutation({
    mutationFn: (market: Market) => call(api.PATCH("/api/v1/auth/me", { body: { market } })),
    onSuccess: (res) => queryClient.setQueryData(meQuery.queryKey, res.data),
  });

  const logout = useMutation({
    mutationFn: () => call(api.POST("/api/v1/auth/logout")),
    onSettled: async () => {
      queryClient.clear();
      await navigate({ to: "/login", search: { error: undefined } });
    },
  });

  return (
    <div className="sm-shell">
      <aside className="sm-sidebar">
        <div className="sm-logo">
          Brand<span>iz</span>
        </div>
        <nav className="sm-nav">
          <Link to="/dashboard" activeProps={{ className: "active" }}>
            Dashboard
          </Link>
          <Link to="/projects" activeProps={{ className: "active" }}>
            Projects
          </Link>
          <div className="sm-nav-section">Keyword research</div>
          <Link to="/keywords/overview" search={{ q: "" }} activeProps={{ className: "active" }}>
            Keyword Overview
          </Link>
          <Link to="/keywords/magic" search={{ seed: "" }} activeProps={{ className: "active" }}>
            Keyword Magic
          </Link>
          <Link to="/keywords/lists" activeProps={{ className: "active" }}>
            Keyword Lists
          </Link>
          <div className="sm-nav-section">Coming soon</div>
          {SOON.map(([label, phase]) => (
            <div key={label} className="sm-soon" title={`Arrives in phase ${phase.slice(1)}`}>
              {label} <span className="sm-tag">{phase}</span>
            </div>
          ))}
          <div className="sm-nav-section">Admin</div>
          <Link to="/admin/usage" activeProps={{ className: "active" }}>
            Cost &amp; cache
          </Link>
        </nav>
      </aside>

      <div>
        <header className="sm-topbar">
          <div className="sm-search">
            <KeywordSearch to="/keywords/overview" market={me.market} compact />
          </div>
          <div className="sm-market">
            <Select
              options={MARKET_OPTIONS}
              value={me.market}
              onChange={(v: string) => setMarket.mutate(v as Market)}
              aria-label="Market"
              w="100%"
            />
          </div>
          <div className="sm-user">
            <span className="sm-user-email" title={me.email}>
              {me.email}
            </span>
            <Button use="secondary" onClick={() => logout.mutate()}>
              Log out
            </Button>
          </div>
        </header>
        <main className="sm-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
