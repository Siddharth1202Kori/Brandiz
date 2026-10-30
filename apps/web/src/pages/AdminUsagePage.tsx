import { DataTable } from "@semcore/ui/data-table";
import Select from "@semcore/ui/select";
import Spin from "@semcore/ui/spin";
import { Text } from "@semcore/ui/typography";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { adminUsageQuery } from "../api/keywords";
import { ErrorNotice } from "../components/keywords";

const DAYS = [1, 7, 30, 90].map((d) => ({
  value: String(d),
  label: `Last ${d} day${d === 1 ? "" : "s"}`,
  children: `Last ${d} day${d === 1 ? "" : "s"}`,
}));
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
const usd = (x: number) => (x < 0.01 && x > 0 ? `$${x.toFixed(5)}` : `$${x.toFixed(2)}`);

/** Cost + cache dashboard over the provider_calls ledger (Phase 1 exit criterion). */
export function AdminUsagePage() {
  const [days, setDays] = useState(7);
  const usage = useQuery(adminUsageQuery(days));

  return (
    <>
      <div className="sm-page-head">
        <Text tag="h1" size={600} bold>
          Provider cost &amp; cache
        </Text>
        <div className="sm-market">
          <Select
            options={DAYS}
            value={String(days)}
            onChange={(v: string) => setDays(Number(v))}
          />
        </div>
      </div>
      {usage.isError && <ErrorNotice error={usage.error} />}
      {usage.isPending && <Spin size="xl" />}
      {usage.data && (
        <>
          <div className="sm-cards">
            <Stat label="Report views" value={usage.data.views.toLocaleString()} />
            <Stat label="Cache hit rate" value={pct(usage.data.hit_rate)} />
            <Stat label="Provider spend" value={usd(usage.data.cost_usd)} />
            <Stat label="Cost per view" value={usd(usage.data.cost_per_view_usd)} />
          </div>
          <div className="sm-panel">
            <Text tag="h3" size={300} bold>
              By endpoint
            </Text>
            <DataTable
              aria-label="Usage by endpoint"
              data={usage.data.by_endpoint.map((e) => ({
                endpoint: `${e.provider} · ${e.endpoint}`,
                views: e.views,
                hits: pct(e.hit_rate),
                calls: e.provider_calls,
                cost: usd(e.cost_usd),
                per_view: usd(e.cost_per_view_usd),
                latency: `${Math.round(e.avg_latency_ms)} ms`,
              }))}
              columns={[
                { name: "endpoint", children: "Endpoint", gtcWidth: "minmax(200px, 2fr)" },
                { name: "views", children: "Views", justifyContent: "right" },
                { name: "hits", children: "Hit rate", justifyContent: "right" },
                { name: "calls", children: "Paid calls", justifyContent: "right" },
                { name: "cost", children: "Spend", justifyContent: "right" },
                { name: "per_view", children: "Per view", justifyContent: "right" },
                { name: "latency", children: "Avg latency", justifyContent: "right" },
              ]}
            />
          </div>
          <div className="sm-panel">
            <Text tag="h3" size={300} bold>
              Recent lookups
            </Text>
            <DataTable
              aria-label="Recent provider lookups"
              data={usage.data.recent.map((r) => ({
                at: new Date(r.created_at).toLocaleTimeString(),
                endpoint: r.endpoint,
                key: r.cache_key,
                tier: r.cache_tier,
                cost: usd(r.cost_usd),
                ms: r.latency_ms,
              }))}
              columns={[
                { name: "at", children: "Time" },
                { name: "endpoint", children: "Endpoint" },
                { name: "key", children: "Cache key", gtcWidth: "minmax(200px, 3fr)" },
                { name: "tier", children: "Tier" },
                { name: "cost", children: "Cost", justifyContent: "right" },
                { name: "ms", children: "ms", justifyContent: "right" },
              ]}
            />
          </div>
        </>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="sm-panel sm-card">
      <span className="sm-card-label">{label}</span>
      <span className="sm-big">{value}</span>
    </div>
  );
}
