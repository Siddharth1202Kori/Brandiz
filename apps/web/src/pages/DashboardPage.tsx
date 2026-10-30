import { Text } from "@semcore/ui/typography";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { meQuery, projectsQuery } from "../api/queries";
import { LimitsWidget } from "../components/LimitsWidget";

export function DashboardPage() {
  const { data: me } = useSuspenseQuery(meQuery);
  const projects = useQuery(projectsQuery);

  return (
    <>
      <Text tag="h1" size={600} bold>
        Welcome{me.name ? `, ${me.name}` : ""}
      </Text>
      <div className="sm-panel">
        <Text tag="h3" size={300} bold>
          Getting started
        </Text>
        <ol>
          <li>
            {projects.data?.length ? "✓ " : ""}
            <Link to="/projects">Create a project</Link> for your website
          </li>
          <li>
            Research keywords with{" "}
            <Link to="/keywords/overview" search={{ q: "" }}>
              Keyword Overview
            </Link>{" "}
            and{" "}
            <Link to="/keywords/magic" search={{ seed: "" }}>
              Keyword Magic
            </Link>
            , then save them to a <Link to="/keywords/lists">list</Link>
          </li>
          <li>Connect Google Search Console — Phase 4</li>
          <li>Track rankings and audit your site — Phases 5–6</li>
        </ol>
      </div>
      <LimitsWidget />
    </>
  );
}
