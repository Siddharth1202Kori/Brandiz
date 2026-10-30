import { DataTable } from "@semcore/ui/data-table";
import Notice from "@semcore/ui/notice";
import Spin from "@semcore/ui/spin";
import { Text } from "@semcore/ui/typography";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, getRouteApi } from "@tanstack/react-router";

import { overviewQuery, serpQuery } from "../../api/keywords";
import { meQuery } from "../../api/queries";
import {
  AddToListButton,
  ErrorNotice,
  IntentBadges,
  KdGauge,
  SourceNote,
  TrendBars,
  fmtMoney,
  fmtNum,
} from "../../components/keywords";
import { KeywordSearch } from "../../components/KeywordSearch";
import { MARKET_LABEL, type Market } from "../../markets";

const route = getRouteApi("/app/keywords/overview");

const FEATURE_LABELS: Record<string, string> = {
  people_also_ask: "People also ask",
  related_searches: "Related searches",
  featured_snippet: "Featured snippet",
  local_pack: "Local pack",
  images: "Images",
  video: "Video",
  top_stories: "Top stories",
  shopping: "Shopping",
  knowledge_graph: "Knowledge panel",
  ai_overview: "AI overview",
  paid: "Ads",
};

export function KeywordOverviewPage() {
  const { q, market: m } = route.useSearch();
  const { data: me } = useSuspenseQuery(meQuery);
  const market: Market = m ?? me.market;
  const keyword = q.trim();

  const overview = useQuery({ ...overviewQuery(keyword, market), enabled: keyword !== "" });
  const serp = useQuery({ ...serpQuery(keyword, market), enabled: keyword !== "" });

  if (!keyword) {
    return (
      <>
        <Text tag="h1" size={600} bold>
          Keyword Overview
        </Text>
        <div className="sm-panel">
          <Text tag="p">
            Search volume, difficulty, intent, trend and the top 10 results for any keyword.
          </Text>
          <KeywordSearch to="/keywords/overview" market={market} />
        </div>
      </>
    );
  }

  const k = overview.data?.data;
  const noData = k && k.volume == null && k.kd == null && k.cpc == null;

  return (
    <>
      <div className="sm-page-head">
        <div>
          <Text tag="h1" size={600} bold>
            Keyword Overview: <span className="sm-kw">{keyword}</span>
          </Text>
          <span className="sm-muted">{MARKET_LABEL[market]}</span>{" "}
          <SourceNote meta={overview.data?.meta} />
        </div>
        <div className="sm-form-row">
          <AddToListButton keywords={[keyword]} market={market} />
          <Link className="sm-link-btn" to="/keywords/magic" search={{ seed: keyword, market }}>
            Keyword ideas →
          </Link>
        </div>
      </div>

      {overview.isError && <ErrorNotice error={overview.error} />}
      {overview.isPending && <Spin size="xl" />}
      {noData && (
        <Notice theme="info">
          No search data for “{keyword}” in {MARKET_LABEL[market]} yet. Long-tail phrases often have
          too few searches to report — try a broader keyword.
        </Notice>
      )}

      {k && (
        <div className="sm-cards">
          <div className="sm-panel sm-card">
            <span className="sm-card-label">Volume</span>
            <span className="sm-big">{fmtNum(k.volume)}</span>
            <span className="sm-muted sm-small">monthly searches</span>
          </div>
          <div className="sm-panel sm-card">
            <span className="sm-card-label">Keyword difficulty</span>
            <KdGauge kd={k.kd} />
          </div>
          <div className="sm-panel sm-card">
            <span className="sm-card-label">CPC</span>
            <span className="sm-big">{fmtMoney(k.cpc)}</span>
            <span className="sm-muted sm-small">
              Competition {k.competition == null ? "—" : k.competition.toFixed(2)}
            </span>
          </div>
          <div className="sm-panel sm-card">
            <span className="sm-card-label">Intent</span>
            <IntentBadges intents={k.intents} />
            <span className="sm-small">{k.intents?.join(", ")}</span>
          </div>
        </div>
      )}

      {k && (
        <div className="sm-panel">
          <Text tag="h3" size={300} bold>
            Trend (last 12 months)
          </Text>
          <TrendBars values={k.trend} months={k.trend_months} height={90} />
          {k.trend_months && k.trend_months.length > 0 && (
            <div className="sm-trend-axis sm-muted sm-small">
              <span>{k.trend_months[0]}</span>
              <span>{k.trend_months[k.trend_months.length - 1]}</span>
            </div>
          )}
        </div>
      )}

      <div className="sm-panel">
        <Text tag="h3" size={300} bold>
          SERP — top 10 organic results
        </Text>
        {serp.isError && <ErrorNotice error={serp.error} />}
        {serp.data && serp.data.data.features && serp.data.data.features.length > 0 && (
          <div className="sm-chips">
            {serp.data.data.features.map((f) => (
              <span key={f} className="sm-chip">
                {FEATURE_LABELS[f] ?? f.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}
        <DataTable
          aria-label="Top 10 search results"
          w="100%"
          loading={serp.isPending}
          data={(serp.data?.data.items ?? []).map((i) => ({
            position: i.position,
            page: i.url,
            title: i.title ?? "",
            domain: i.domain,
          }))}
          renderCell={(props) => {
            if (props.dataKey === "page") {
              const url = String(props.row.page);
              return (
                <div className="sm-serp-cell">
                  <a href={url} target="_blank" rel="noreferrer noopener">
                    {String(props.row.title) || url}
                  </a>
                  <span className="sm-muted sm-small sm-ellipsis">{url}</span>
                </div>
              );
            }
            return props.defaultRender();
          }}
          columns={[
            { name: "position", children: "#", gtcWidth: "48px" },
            { name: "page", children: "Page", gtcWidth: "minmax(0, 3fr)" },
            { name: "domain", children: "Domain", gtcWidth: "minmax(0, 1fr)" },
          ]}
        />
      </div>
    </>
  );
}
