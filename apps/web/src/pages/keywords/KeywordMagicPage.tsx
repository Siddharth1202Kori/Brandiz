import Button from "@semcore/ui/button";
import Checkbox from "@semcore/ui/checkbox";
import { DataTable } from "@semcore/ui/data-table";
import Input from "@semcore/ui/input";
import Pagination from "@semcore/ui/pagination";
import TabLine from "@semcore/ui/tab-line";
import { Text } from "@semcore/ui/typography";
import { useMutation, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { downloadCsv, ideasQuery, type IdeasMode, type IdeasParams } from "../../api/keywords";
import { meQuery } from "../../api/queries";
import {
  AddToListButton,
  ErrorNotice,
  IntentBadges,
  KdBadge,
  SourceNote,
  TrendBars,
  UpsellNotice,
  fmtMoney,
  fmtNum,
} from "../../components/keywords";
import { KeywordSearch } from "../../components/KeywordSearch";
import { MARKET_LABEL, type Market } from "../../markets";

const route = getRouteApi("/app/keywords/magic");
const PAGE_SIZE = 50;
const MODES: [IdeasMode, string][] = [
  ["ideas", "Broad ideas"],
  ["related", "Related"],
  ["suggestions", "Contains seed"],
];
const INTENTS = ["informational", "navigational", "commercial", "transactional"];
type SortField = NonNullable<IdeasParams["sort"]>;
const SORTABLE: SortField[] = ["keyword", "volume", "kd", "cpc", "competition"];

type FilterForm = Record<
  | "volume_min"
  | "volume_max"
  | "kd_min"
  | "kd_max"
  | "cpc_min"
  | "cpc_max"
  | "words_min"
  | "words_max"
  | "include"
  | "exclude",
  string
>;

const num = (s: string) => (s.trim() === "" || Number.isNaN(Number(s)) ? undefined : Number(s));
const words = (s: string) =>
  s
    .split(",")
    .map((w) => w.trim())
    .filter(Boolean);

export function KeywordMagicPage() {
  const search = route.useSearch();
  const navigate = useNavigate({ from: "/keywords/magic" });
  const { data: me } = useSuspenseQuery(meQuery);
  const market: Market = search.market ?? me.market;
  const seed = search.seed.trim();
  const page = search.page ?? 1;

  const params: IdeasParams = {
    seed,
    market,
    mode: search.mode ?? "ideas",
    sort: search.sort ?? "volume",
    dir: search.dir ?? "desc",
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    volume_min: search.volume_min,
    volume_max: search.volume_max,
    kd_min: search.kd_min,
    kd_max: search.kd_max,
    cpc_min: search.cpc_min,
    cpc_max: search.cpc_max,
    words_min: search.words_min,
    words_max: search.words_max,
    intent: search.intent,
    include: search.include,
    exclude: search.exclude,
  };
  const ideas = useQuery({ ...ideasQuery(params), enabled: seed !== "" });
  const [selected, setSelected] = useState<string[]>([]);

  const [form, setForm] = useState<FilterForm>(() => ({
    volume_min: search.volume_min?.toString() ?? "",
    volume_max: search.volume_max?.toString() ?? "",
    kd_min: search.kd_min?.toString() ?? "",
    kd_max: search.kd_max?.toString() ?? "",
    cpc_min: search.cpc_min?.toString() ?? "",
    cpc_max: search.cpc_max?.toString() ?? "",
    words_min: search.words_min?.toString() ?? "",
    words_max: search.words_max?.toString() ?? "",
    include: (search.include ?? []).join(", "),
    exclude: (search.exclude ?? []).join(", "),
  }));
  const [intents, setIntents] = useState<string[]>(search.intent ?? []);
  const set = (k: keyof FilterForm) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const exportCsv = useMutation({
    mutationFn: () => {
      const rest: Record<string, unknown> = { ...params };
      delete rest.offset;
      delete rest.limit;
      return downloadCsv("/api/v1/keywords/ideas/export.csv", rest);
    },
  });

  if (!seed) {
    return (
      <>
        <Text tag="h1" size={600} bold>
          Keyword Magic Tool
        </Text>
        <div className="sm-panel">
          <Text tag="p">
            Find hundreds of keyword ideas from one seed keyword, then filter and save them.
          </Text>
          <KeywordSearch to="/keywords/magic" market={market} />
        </div>
      </>
    );
  }

  const applyFilters = (e: FormEvent) => {
    e.preventDefault();
    setSelected([]);
    void navigate({
      search: (s) => ({
        ...s,
        page: 1,
        volume_min: num(form.volume_min),
        volume_max: num(form.volume_max),
        kd_min: num(form.kd_min),
        kd_max: num(form.kd_max),
        cpc_min: num(form.cpc_min),
        cpc_max: num(form.cpc_max),
        words_min: num(form.words_min),
        words_max: num(form.words_max),
        intent: intents.length ? intents : undefined,
        include: words(form.include).length ? words(form.include) : undefined,
        exclude: words(form.exclude).length ? words(form.exclude) : undefined,
      }),
    });
  };

  const resetFilters = () => {
    setForm({
      volume_min: "",
      volume_max: "",
      kd_min: "",
      kd_max: "",
      cpc_min: "",
      cpc_max: "",
      words_min: "",
      words_max: "",
      include: "",
      exclude: "",
    });
    setIntents([]);
    void navigate({ search: { seed, market, mode: params.mode } });
  };

  const rows = ideas.data?.data ?? [];
  const meta = ideas.data?.meta;
  const total = meta?.page?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const byKeyword = new Map(rows.map((r) => [r.keyword, r]));

  return (
    <>
      <div className="sm-page-head">
        <div>
          <Text tag="h1" size={600} bold>
            Keyword Magic: <span className="sm-kw">{seed}</span>
          </Text>
          <span className="sm-muted">
            {MARKET_LABEL[market]} · {total.toLocaleString()} keywords
          </span>{" "}
          <SourceNote meta={meta} />
        </div>
        <div className="sm-form-row">
          <AddToListButton keywords={selected} market={market} />
          <Button use="secondary" loading={exportCsv.isPending} onClick={() => exportCsv.mutate()}>
            Export CSV
          </Button>
        </div>
      </div>

      <TabLine
        value={params.mode}
        onChange={(v: string | number | boolean) => {
          setSelected([]);
          void navigate({ search: (s) => ({ ...s, mode: v as IdeasMode, page: 1 }) });
        }}
        aria-label="Idea type"
      >
        {MODES.map(([value, label]) => (
          <TabLine.Item key={value} value={value}>
            {label}
          </TabLine.Item>
        ))}
      </TabLine>

      <form className="sm-panel sm-filters" onSubmit={applyFilters} aria-label="Filters">
        <Range
          label="Volume"
          min={form.volume_min}
          max={form.volume_max}
          onMin={set("volume_min")}
          onMax={set("volume_max")}
        />
        <Range
          label="KD %"
          min={form.kd_min}
          max={form.kd_max}
          onMin={set("kd_min")}
          onMax={set("kd_max")}
        />
        <Range
          label="CPC $"
          min={form.cpc_min}
          max={form.cpc_max}
          onMin={set("cpc_min")}
          onMax={set("cpc_max")}
        />
        <Range
          label="Words"
          min={form.words_min}
          max={form.words_max}
          onMin={set("words_min")}
          onMax={set("words_max")}
        />
        <label className="sm-field">
          Include (all of)
          <Input>
            <Input.Value
              value={form.include}
              onChange={set("include")}
              placeholder="free, online"
            />
          </Input>
        </label>
        <label className="sm-field">
          Exclude (any of)
          <Input>
            <Input.Value
              value={form.exclude}
              onChange={set("exclude")}
              placeholder="jobs, salary"
            />
          </Input>
        </label>
        <fieldset className="sm-field sm-intent-filter">
          <legend>Intent</legend>
          {INTENTS.map((i) => (
            <Checkbox
              key={i}
              label={i[0].toUpperCase() + i.slice(1)}
              checked={intents.includes(i)}
              onChange={(on: boolean) =>
                setIntents((cur) => (on ? [...cur, i] : cur.filter((x) => x !== i)))
              }
            />
          ))}
        </fieldset>
        <div className="sm-form-row">
          <Button type="submit" use="primary">
            Apply
          </Button>
          <Button type="button" use="tertiary" onClick={resetFilters}>
            Reset
          </Button>
        </div>
      </form>

      {ideas.isError && <ErrorNotice error={ideas.error} />}
      {exportCsv.isError && <ErrorNotice error={exportCsv.error} />}
      {meta?.limited && <UpsellNotice shown={(params.offset ?? 0) + rows.length} total={total} />}

      <div className="sm-panel">
        <DataTable
          aria-label="Keyword ideas"
          w="100%"
          loading={ideas.isFetching}
          data={rows.map((r) => ({
            keyword: r.keyword,
            intent: r.intents?.join(",") ?? "",
            volume: r.volume ?? "",
            trend: "",
            kd: r.kd ?? "",
            cpc: r.cpc ?? "",
            competition: r.competition ?? "",
          }))}
          uniqueRowKey="keyword"
          selectedRows={selected}
          onSelectedRowsChange={(keys: string[]) => setSelected(keys)}
          sort={[params.sort as SortField, params.dir ?? "desc"]}
          onSortChange={([field, dir]) => {
            if (!SORTABLE.includes(field as SortField)) return;
            void navigate({ search: (s) => ({ ...s, sort: field as SortField, dir, page: 1 }) });
          }}
          renderEmptyData={() => (
            <div className="sm-empty">
              {ideas.isPending ? "Loading…" : "No keywords match these filters."}
            </div>
          )}
          renderCell={(props) => {
            const r = byKeyword.get(String(props.row.keyword));
            if (!r) return props.defaultRender();
            switch (props.dataKey) {
              case "keyword":
                return (
                  <Link to="/keywords/overview" search={{ q: r.keyword, market }}>
                    {r.keyword}
                  </Link>
                );
              case "intent":
                return <IntentBadges intents={r.intents} />;
              case "volume":
                return fmtNum(r.volume);
              case "trend":
                return <TrendBars values={r.trend} months={r.trend_months} height={22} />;
              case "kd":
                return <KdBadge kd={r.kd} />;
              case "cpc":
                return fmtMoney(r.cpc);
              case "competition":
                return r.competition == null ? "—" : r.competition.toFixed(2);
              default:
                return props.defaultRender();
            }
          }}
          columns={[
            {
              name: "keyword",
              children: "Keyword",
              sortable: true,
              changeSortSize: true,
              gtcWidth: "minmax(180px, 3fr)",
            },
            { name: "intent", children: "Intent", gtcWidth: "90px" },
            {
              name: "volume",
              children: "Volume",
              sortable: true,
              changeSortSize: true,
              justifyContent: "right",
              gtcWidth: "120px",
            },
            { name: "trend", children: "Trend", gtcWidth: "110px" },
            {
              name: "kd",
              children: "KD %",
              sortable: true,
              changeSortSize: true,
              justifyContent: "right",
              gtcWidth: "90px",
            },
            {
              name: "cpc",
              children: "CPC",
              sortable: true,
              changeSortSize: true,
              justifyContent: "right",
              gtcWidth: "90px",
            },
            {
              name: "competition",
              children: "Com.",
              sortable: true,
              changeSortSize: true,
              justifyContent: "right",
              gtcWidth: "70px",
            },
          ]}
        />
        {totalPages > 1 && (
          <div className="sm-pager">
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onCurrentPageChange={(p: number) =>
                void navigate({ search: (s) => ({ ...s, page: p }) })
              }
            />
          </div>
        )}
      </div>
    </>
  );
}

function Range(props: {
  label: string;
  min: string;
  max: string;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
}) {
  return (
    <div className="sm-field">
      {props.label}
      <div className="sm-range">
        <Input>
          <Input.Value
            value={props.min}
            onChange={props.onMin}
            placeholder="From"
            inputMode="decimal"
            aria-label={`${props.label} from`}
          />
        </Input>
        <Input>
          <Input.Value
            value={props.max}
            onChange={props.onMax}
            placeholder="To"
            inputMode="decimal"
            aria-label={`${props.label} to`}
          />
        </Input>
      </div>
    </div>
  );
}
