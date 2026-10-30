import Button from "@semcore/ui/button";
import { DataTable } from "@semcore/ui/data-table";
import Notice from "@semcore/ui/notice";
import Spin from "@semcore/ui/spin";
import { Text } from "@semcore/ui/typography";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, getRouteApi, useNavigate } from "@tanstack/react-router";

import { api, call } from "../../api/client";
import { downloadCsv, listQuery, listsQuery } from "../../api/keywords";
import { limitsQuery } from "../../api/queries";
import { ErrorNotice, IntentBadges, KdBadge, fmtMoney, fmtNum } from "../../components/keywords";
import { MARKET_LABEL } from "../../markets";

const route = getRouteApi("/app/keywords/lists/$listId");

export function ListDetailPage() {
  const { listId } = route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const detail = useQuery(listQuery(listId));

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["kw-list", listId] });
    await queryClient.invalidateQueries({ queryKey: listsQuery.queryKey });
  };

  const remove = useMutation({
    mutationFn: (itemId: string) =>
      call(
        api.DELETE("/api/v1/keywords/lists/{list_id}/items/{item_id}", {
          params: { path: { list_id: listId, item_id: itemId } },
        }),
      ),
    onSuccess: refresh,
  });

  const drop = useMutation({
    mutationFn: () =>
      call(
        api.DELETE("/api/v1/keywords/lists/{list_id}", { params: { path: { list_id: listId } } }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: listsQuery.queryKey });
      await queryClient.invalidateQueries({ queryKey: limitsQuery.queryKey });
      await navigate({ to: "/keywords/lists" });
    },
  });

  const exportCsv = useMutation({
    mutationFn: () => downloadCsv(`/api/v1/keywords/lists/${listId}/export.csv`, {}),
  });

  if (detail.isPending) return <Spin size="xl" />;
  if (detail.isError) return <ErrorNotice error={detail.error} />;

  const { info, items } = detail.data;
  const pending = items.filter((i) => !i.metrics_updated_at).length;

  return (
    <>
      <div className="sm-page-head">
        <div>
          <Link to="/keywords/lists" className="sm-small">
            ← All lists
          </Link>
          <Text tag="h1" size={600} bold>
            {info.name}
          </Text>
          <span className="sm-muted">
            {MARKET_LABEL[info.market]} · {items.length} keywords
          </span>
        </div>
        <div className="sm-form-row">
          <Button
            use="secondary"
            loading={exportCsv.isPending}
            disabled={!items.length}
            onClick={() => exportCsv.mutate()}
          >
            Export CSV
          </Button>
          <Button
            use="tertiary"
            theme="danger"
            loading={drop.isPending}
            onClick={() => drop.mutate()}
          >
            Delete list
          </Button>
        </div>
      </div>
      {exportCsv.isError && <ErrorNotice error={exportCsv.error} />}
      {remove.isError && <ErrorNotice error={remove.error} />}
      {pending > 0 && (
        <Notice theme="info">
          Fetching metrics for {pending} new keyword{pending === 1 ? "" : "s"} — this runs in the
          background and usually finishes within 15–20 minutes.
        </Notice>
      )}

      <div className="sm-panel">
        <DataTable
          aria-label={`Keywords in ${info.name}`}
          data={items.map((i) => ({
            id: i.id,
            keyword: i.keyword,
            intent: "",
            volume: i.volume ?? "",
            kd: i.kd ?? "",
            cpc: i.cpc ?? "",
            updated: i.metrics_updated_at
              ? new Date(i.metrics_updated_at).toLocaleDateString()
              : "pending",
            actions: "",
          }))}
          renderEmptyData={() => <div className="sm-empty">This list is empty.</div>}
          renderCell={(p) => {
            const item = items.find((i) => i.id === p.row.id);
            if (!item) return p.defaultRender();
            switch (p.dataKey) {
              case "keyword":
                return (
                  <Link to="/keywords/overview" search={{ q: item.keyword, market: info.market }}>
                    {item.keyword}
                  </Link>
                );
              case "intent":
                return <IntentBadges intents={item.intents} />;
              case "volume":
                return fmtNum(item.volume);
              case "kd":
                return <KdBadge kd={item.kd} />;
              case "cpc":
                return fmtMoney(item.cpc);
              case "actions":
                return (
                  <Button
                    use="tertiary"
                    size="m"
                    aria-label={`Remove ${item.keyword}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(item.id)}
                  >
                    Remove
                  </Button>
                );
              default:
                return p.defaultRender();
            }
          }}
          columns={[
            { name: "keyword", children: "Keyword", gtcWidth: "minmax(180px, 3fr)" },
            { name: "intent", children: "Intent" },
            { name: "volume", children: "Volume", justifyContent: "right" },
            { name: "kd", children: "KD %", justifyContent: "right" },
            { name: "cpc", children: "CPC", justifyContent: "right" },
            { name: "updated", children: "Updated" },
            { name: "actions", children: "", gtcWidth: "100px" },
          ]}
        />
      </div>
    </>
  );
}
