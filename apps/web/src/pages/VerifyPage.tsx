import Notice from "@semcore/ui/notice";
import Spin from "@semcore/ui/spin";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useEffect, useRef } from "react";

import { api, call } from "../api/client";
import { meQuery } from "../api/queries";

export function VerifyPage() {
  const { token } = useSearch({ from: "/verify" });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sent = useRef(false); // React StrictMode runs effects twice in dev; verify once

  const verify = useMutation({
    mutationFn: () => call(api.POST("/api/v1/auth/verify", { body: { token } })),
    onSuccess: async (res) => {
      queryClient.setQueryData(meQuery.queryKey, res.data);
      await navigate({ to: "/dashboard" });
    },
  });

  const { mutate } = verify;
  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    mutate();
  }, [token, mutate]);

  return (
    <div className="sm-auth">
      <div className="sm-auth-card">
        {verify.isError || !token ? (
          <>
            <Notice>This verification link is invalid or expired.</Notice>
            <Link to="/login" search={{ error: undefined }}>
              Back to sign in (you can request a new link there)
            </Link>
          </>
        ) : (
          <Spin />
        )}
      </div>
    </div>
  );
}
