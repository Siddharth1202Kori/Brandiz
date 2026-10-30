import ProgressBar from "@semcore/ui/progress-bar";
import Spin from "@semcore/ui/spin";
import { Text } from "@semcore/ui/typography";
import { useQuery } from "@tanstack/react-query";

import { limitsQuery } from "../api/queries";

const LABELS: Record<string, string> = {
  reports_per_day: "Reports today",
  keyword_ideas_rows: "Keyword idea rows today",
  exports_per_day: "Exports today",
  audit_pages: "Audit pages this month",
  projects: "Projects",
  keyword_lists: "Keyword lists",
  rank_keywords: "Tracked keywords",
  gsc_sites: "Search Console sites",
};

export function LimitsWidget() {
  const { data, isPending, isError } = useQuery(limitsQuery);

  if (isPending) return <Spin />;
  if (isError) return <Text>Could not load limits.</Text>;

  return (
    <div className="sm-panel">
      <Text tag="h3" size={300} bold>
        Plan: {data.plan_id} — usage
      </Text>
      <div className="sm-grid" style={{ marginTop: 12 }}>
        {data.limits.map((l) => {
          const pct = l.max > 0 ? Math.min(100, Math.round((l.used / l.max) * 100)) : 0;
          return (
            <div key={l.name} className="sm-limit">
              <div className="sm-limit-head">
                <span>{LABELS[l.name] ?? l.name}</span>
                <span>
                  {l.used} / {l.max}
                </span>
              </div>
              <ProgressBar value={pct} aria-label={LABELS[l.name] ?? l.name} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
