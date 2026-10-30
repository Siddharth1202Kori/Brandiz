import Button from "@semcore/ui/button";
import Input from "@semcore/ui/input";
import { useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import type { Market } from "../markets";

/** Keyword input that opens Keyword Overview (q=) or Keyword Magic (seed=). */
export function KeywordSearch({
  to,
  market,
  initial = "",
  compact = false,
}: {
  to: "/keywords/overview" | "/keywords/magic";
  market: Market;
  initial?: string;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const [value, setValue] = useState(initial);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const kw = value.trim();
    if (!kw) return;
    if (to === "/keywords/overview") void navigate({ to, search: { q: kw, market } });
    else void navigate({ to, search: { seed: kw, market } });
  };

  return (
    <form className="sm-search-form" onSubmit={submit} role="search">
      <Input>
        <Input.Value
          value={value}
          onChange={setValue}
          placeholder="Enter a keyword, e.g. seo tools"
          aria-label="Keyword"
        />
      </Input>
      {!compact && (
        <Button type="submit" use="primary">
          Search
        </Button>
      )}
    </form>
  );
}
