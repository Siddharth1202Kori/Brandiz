import Notice from "@semcore/ui/notice";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { healthQuery } from "../api/queries";

/** Free hosting sleeps the API after ~15 min idle; explain the 30-60 s cold start. */
export function WakeBanner() {
  const health = useQuery(healthQuery);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!health.isPending) return;
    const t = setTimeout(() => setSlow(true), 1500);
    return () => clearTimeout(t);
  }, [health.isPending]);

  if (!health.isPending || !slow) return null;
  return (
    <div className="sm-banner">
      <Notice>
        Waking up the server… free hosting sleeps when idle, this can take up to a minute.
      </Notice>
    </div>
  );
}
