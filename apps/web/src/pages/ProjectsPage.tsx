import Button from "@semcore/ui/button";
import { DataTable } from "@semcore/ui/data-table";
import Input from "@semcore/ui/input";
import Notice from "@semcore/ui/notice";
import Select from "@semcore/ui/select";
import { Text } from "@semcore/ui/typography";
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError, api, call } from "../api/client";
import { limitsQuery, meQuery, projectsQuery } from "../api/queries";
import { MARKET_OPTIONS, type Market } from "../markets";

const ERRORS: Record<string, string> = {
  quota_exceeded: "Your plan's project limit is reached. Upgrade to add more.",
  invalid_domain: "Enter a valid domain, e.g. example.com",
  project_exists: "A project for this domain and market already exists.",
};

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const projects = useQuery(projectsQuery);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const { data: me } = useSuspenseQuery(meQuery);
  const [market, setMarket] = useState<Market>(me.market); // default to the user's market

  const create = useMutation({
    mutationFn: () => call(api.POST("/api/v1/projects", { body: { name, domain, market } })),
    onSuccess: async () => {
      setName("");
      setDomain("");
      await queryClient.invalidateQueries({ queryKey: projectsQuery.queryKey });
      await queryClient.invalidateQueries({ queryKey: limitsQuery.queryKey });
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  const rows = (projects.data ?? []).map((p) => ({
    name: p.name,
    domain: p.domain,
    market: p.market.toUpperCase(),
    created: new Date(p.created_at).toLocaleDateString(),
  }));

  return (
    <>
      <Text tag="h1" size={600} bold>
        Projects
      </Text>

      <form className="sm-panel sm-form-row" onSubmit={submit}>
        <label className="sm-field">
          Name
          <Input>
            <Input.Value value={name} onChange={setName} placeholder="My site" />
          </Input>
        </label>
        <label className="sm-field">
          Domain
          <Input>
            <Input.Value value={domain} onChange={setDomain} placeholder="example.com" />
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
        <Button type="submit" use="primary" loading={create.isPending}>
          Create project
        </Button>
      </form>
      {create.error instanceof ApiError && (
        <Notice>{ERRORS[create.error.code] ?? create.error.message}</Notice>
      )}

      <div className="sm-panel">
        {!projects.isPending && rows.length === 0 ? (
          <Text>No projects yet. Add your website above to get started.</Text>
        ) : (
          <DataTable
            data={rows}
            aria-label="Projects"
            loading={projects.isPending}
            columns={[
              { name: "name", children: "Name" },
              { name: "domain", children: "Domain" },
              { name: "market", children: "Market" },
              { name: "created", children: "Created" },
            ]}
          />
        )}
      </div>
    </>
  );
}
