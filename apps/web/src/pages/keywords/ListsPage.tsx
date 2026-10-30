import Button from "@semcore/ui/button";
import { DataTable } from "@semcore/ui/data-table";
import Input from "@semcore/ui/input";
import Select from "@semcore/ui/select";
import { Text } from "@semcore/ui/typography";
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { api, call } from "../../api/client";
import { listsQuery } from "../../api/keywords";
import { limitsQuery, meQuery } from "../../api/queries";
import { ErrorNotice } from "../../components/keywords";
import { MARKET_LABEL, MARKET_OPTIONS, type Market } from "../../markets";

export function ListsPage() {
  const queryClient = useQueryClient();
  const { data: me } = useSuspenseQuery(meQuery);
  const lists = useQuery(listsQuery);
  const [name, setName] = useState("");
  const [market, setMarket] = useState<Market>(me.market);

  const create = useMutation({
    mutationFn: () =>
      call(api.POST("/api/v1/keywords/lists", { body: { name: name.trim(), market } })),
    onSuccess: async () => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: listsQuery.queryKey });
      await queryClient.invalidateQueries({ queryKey: limitsQuery.queryKey });
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) create.mutate();
  };

  const data = lists.data ?? [];
  return (
    <>
      <Text tag="h1" size={600} bold>
        Keyword lists
      </Text>
      <form className="sm-panel sm-form-row" onSubmit={submit}>
        <label className="sm-field">
          Name
          <Input>
            <Input.Value value={name} onChange={setName} placeholder="e.g. Blog ideas" />
          </Input>
        </label>
        <label className="sm-field">
          Market
          <Select
            options={MARKET_OPTIONS}
            value={market}
            onChange={(v: string) => setMarket(v as Market)}
          />
        </label>
        <Button type="submit" use="primary" loading={create.isPending} disabled={!name.trim()}>
          Create list
        </Button>
      </form>
      {create.isError && <ErrorNotice error={create.error} />}

      <div className="sm-panel">
        {!lists.isPending && data.length === 0 ? (
          <Text>
            No lists yet. Create one here, or use “Add to list” in Keyword Overview / Keyword Magic.
          </Text>
        ) : (
          <DataTable
            aria-label="Keyword lists"
            loading={lists.isPending}
            data={data.map((l) => ({
              id: l.id,
              name: l.name,
              market: MARKET_LABEL[l.market],
              items: l.item_count ?? 0,
              created: new Date(l.created_at).toLocaleDateString(),
            }))}
            renderCell={(p) =>
              p.dataKey === "name" ? (
                <Link to="/keywords/lists/$listId" params={{ listId: String(p.row.id) }}>
                  {String(p.row.name)}
                </Link>
              ) : (
                p.defaultRender()
              )
            }
            columns={[
              { name: "name", children: "List" },
              { name: "market", children: "Market" },
              { name: "items", children: "Keywords", justifyContent: "right" },
              { name: "created", children: "Created" },
            ]}
          />
        )}
      </div>
    </>
  );
}
