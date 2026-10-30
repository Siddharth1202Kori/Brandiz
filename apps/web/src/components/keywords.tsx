import Button from "@semcore/ui/button";
import Input from "@semcore/ui/input";
import Modal from "@semcore/ui/modal";
import Notice from "@semcore/ui/notice";
import Select from "@semcore/ui/select";
import { Text } from "@semcore/ui/typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api, call } from "../api/client";
import { listsQuery } from "../api/keywords";
import { limitsQuery } from "../api/queries";
import type { Market } from "../markets";

// -- formatting --------------------------------------------------------------------------------

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** Unknown is "—", never 0 (doc rule: 0 volume ≠ no data). */
export function fmtNum(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n >= 10_000 ? compact.format(n) : n.toLocaleString();
}

export function fmtMoney(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `$${n.toFixed(2)}`;
}

// -- keyword difficulty --------------------------------------------------------------------------

const KD_BUCKETS: [number, string, string][] = [
  [15, "Very easy", "#16a34a"],
  [30, "Easy", "#65a30d"],
  [50, "Possible", "#ca8a04"],
  [70, "Difficult", "#ea580c"],
  [85, "Hard", "#dc2626"],
  [101, "Very hard", "#991b1b"],
];

export function kdBucket(kd: number): { label: string; color: string } {
  const [, label, color] =
    KD_BUCKETS.find(([max]) => kd < max) ?? KD_BUCKETS[KD_BUCKETS.length - 1];
  return { label, color };
}

export function KdBadge({ kd }: { kd: number | null | undefined }) {
  if (kd === null || kd === undefined) return <span className="sm-muted">—</span>;
  const { label, color } = kdBucket(kd);
  return (
    <span className="sm-kd" title={label}>
      <span className="sm-dot" style={{ background: color }} />
      {kd}
    </span>
  );
}

/** Half-circle gauge, 0–100. */
export function KdGauge({ kd }: { kd: number | null | undefined }) {
  const r = 52;
  const half = Math.PI * r;
  const value = kd ?? 0;
  const { label, color } = kdBucket(value);
  return (
    <div className="sm-gauge">
      <svg
        viewBox="0 0 120 68"
        width="160"
        role="img"
        aria-label={`Keyword difficulty ${kd ?? "unknown"}`}
      >
        <path d="M8 60 A52 52 0 0 1 112 60" fill="none" stroke="#e5e7eb" strokeWidth="12" />
        {kd !== null && kd !== undefined && (
          <path
            d="M8 60 A52 52 0 0 1 112 60"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeDasharray={`${(half * value) / 100} ${half}`}
          />
        )}
        <text x="60" y="56" textAnchor="middle" fontSize="22" fontWeight="700" fill="#191b23">
          {kd ?? "—"}
        </text>
      </svg>
      <span style={{ color: kd === null || kd === undefined ? "#6b7280" : color }}>
        {kd === null || kd === undefined ? "No data" : label}
      </span>
    </div>
  );
}

// -- intent ----------------------------------------------------------------------------------------

const INTENT: Record<string, [string, string]> = {
  informational: ["I", "#2563eb"],
  navigational: ["N", "#7c3aed"],
  commercial: ["C", "#ca8a04"],
  transactional: ["T", "#16a34a"],
};

export function IntentBadges({ intents }: { intents: string[] | undefined }) {
  if (!intents?.length) return <span className="sm-muted">—</span>;
  return (
    <span className="sm-intents">
      {intents.map((i) => {
        const [letter, color] = INTENT[i] ?? ["?", "#6b7280"];
        return (
          <span key={i} className="sm-intent" style={{ color, borderColor: color }} title={i}>
            {letter}
          </span>
        );
      })}
    </span>
  );
}

// -- trend -----------------------------------------------------------------------------------------

export function TrendBars({
  values,
  months,
  height = 64,
}: {
  values: (number | null)[] | undefined;
  months?: string[];
  height?: number;
}) {
  if (!values?.length) return <span className="sm-muted">No trend data</span>;
  const max = Math.max(1, ...values.map((v) => v ?? 0));
  const w = 100 / values.length;
  return (
    <svg
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      width="100%"
      height={height}
      role="img"
      aria-label="Monthly search volume, last 12 months"
    >
      {values.map((v, i) => {
        const h = v === null ? 2 : Math.max(2, (v / max) * (height - 2));
        return (
          <rect
            key={i}
            x={i * w + w * 0.15}
            y={height - h}
            width={w * 0.7}
            height={h}
            fill={v === null ? "#e5e7eb" : "var(--sm-brand)"}
            rx="0.6"
          >
            <title>{`${months?.[i] ?? ""}: ${v === null ? "no data" : v.toLocaleString()}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

// -- notices ---------------------------------------------------------------------------------------

const ERRORS: Record<string, string> = {
  quota_exceeded: "You've reached your plan's limit for today.",
  budget_exceeded: "Data is temporarily unavailable. Please try again later.",
  provider_error: "Our keyword data provider didn't respond. Please try again shortly.",
  invalid_keyword: "Enter a keyword to analyze.",
};

const METRICS: Record<string, string> = {
  reports_per_day: "reports per day",
  keyword_ideas_rows: "keyword idea rows per day",
  exports_per_day: "exports per day",
  keyword_lists: "keyword lists",
};

export function errorText(err: unknown): string {
  if (!(err instanceof ApiError)) return "Something went wrong.";
  if (err.code === "quota_exceeded") {
    const d = err.details as { metric?: string; limit?: number } | undefined;
    const what = METRICS[d?.metric ?? ""] ?? d?.metric ?? "this feature";
    return d?.limit === 0
      ? `Your plan doesn't include ${what}. Upgrade to unlock it.`
      : `Plan limit reached: ${d?.limit} ${what}. Upgrade for more.`;
  }
  return ERRORS[err.code] ?? err.message;
}

export function ErrorNotice({ error }: { error: unknown }) {
  return <Notice theme="warning">{errorText(error)}</Notice>;
}

export function UpsellNotice({ shown, total }: { shown: number; total?: number | null }) {
  return (
    <Notice theme="info">
      Showing the first {shown.toLocaleString()}
      {total ? ` of ${total.toLocaleString()}` : ""} results on your plan. Upgrade to see every
      keyword and export the full list.
    </Notice>
  );
}

export function SourceNote({
  meta,
}: {
  meta?: { cached?: boolean; fetched_at?: string | null; source?: string | null };
}) {
  if (!meta?.fetched_at) return null;
  const when = new Date(meta.fetched_at).toLocaleDateString();
  return (
    <span className="sm-muted sm-small">
      Data as of {when}
      {meta.source === "fake" ? " · demo data (fake provider)" : ""}
    </span>
  );
}

// -- add to list -------------------------------------------------------------------------------------

export function AddToListButton({
  keywords,
  market,
  disabled,
}: {
  keywords: string[];
  market: Market;
  disabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [listId, setListId] = useState<string>("");
  const [newName, setNewName] = useState("");
  const lists = useQuery({ ...listsQuery, enabled: open });
  const sameMarket = (lists.data ?? []).filter((l) => l.market === market);

  const save = useMutation({
    mutationFn: async () => {
      let id = listId;
      if (!id) {
        const created = await call(
          api.POST("/api/v1/keywords/lists", { body: { name: newName.trim(), market } }),
        );
        id = created.data.id;
      }
      return call(
        api.POST("/api/v1/keywords/lists/{list_id}/items", {
          params: { path: { list_id: id } },
          body: { keywords },
        }),
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: listsQuery.queryKey });
      await queryClient.invalidateQueries({ queryKey: ["kw-list"] });
      await queryClient.invalidateQueries({ queryKey: limitsQuery.queryKey });
    },
  });

  const close = () => {
    setOpen(false);
    save.reset();
  };
  const options = [
    ...sameMarket.map((l) => ({
      value: l.id,
      label: `${l.name} (${l.item_count})`,
      children: `${l.name} (${l.item_count})`,
    })),
    { value: "", label: "+ New list", children: "+ New list" },
  ];
  const canSave = keywords.length > 0 && (listId !== "" || newName.trim() !== "");

  return (
    <>
      <Button
        use="secondary"
        disabled={disabled || keywords.length === 0}
        onClick={() => setOpen(true)}
      >
        Add to list{keywords.length > 1 ? ` (${keywords.length})` : ""}
      </Button>
      <Modal visible={open} onClose={close}>
        <div className="sm-modal">
          <Text tag="h3" size={400} bold>
            Add {keywords.length === 1 ? `"${keywords[0]}"` : `${keywords.length} keywords`} to a
            list
          </Text>
          {save.isSuccess ? (
            <>
              <Notice theme="success">
                Added {save.data.data.added} keyword{save.data.data.added === 1 ? "" : "s"}
                {save.data.data.added < keywords.length ? " (others were already in the list)" : ""}
                .
              </Notice>
              <Button use="primary" onClick={close}>
                Done
              </Button>
            </>
          ) : (
            <>
              <label className="sm-field">
                List ({market.toUpperCase()})
                <Select options={options} value={listId} onChange={(v: string) => setListId(v)} />
              </label>
              {listId === "" && (
                <label className="sm-field">
                  New list name
                  <Input>
                    <Input.Value
                      value={newName}
                      onChange={setNewName}
                      placeholder="e.g. Blog ideas"
                    />
                  </Input>
                </label>
              )}
              {save.isError && <ErrorNotice error={save.error} />}
              <div className="sm-form-row">
                <Button
                  use="primary"
                  disabled={!canSave}
                  loading={save.isPending}
                  onClick={() => save.mutate()}
                >
                  Save
                </Button>
                <Button use="tertiary" onClick={close}>
                  Cancel
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>
    </>
  );
}
