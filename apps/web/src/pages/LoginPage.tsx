import Button from "@semcore/ui/button";
import Input from "@semcore/ui/input";
import Notice from "@semcore/ui/notice";
import { Text } from "@semcore/ui/typography";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { API_BASE, ApiError, api, call } from "../api/client";
import { meQuery } from "../api/queries";
import { ResendVerification } from "../components/ResendVerification";

const MESSAGES: Record<string, string> = {
  google: "Google sign-in failed. Try again or use email.",
  invalid_credentials: "Wrong email or password.",
  email_not_verified: "Verify your email first - check the link we sent you.",
  rate_limited: "Too many attempts. Wait a minute and try again.",
};

export function LoginPage() {
  const { error: urlError } = useSearch({ from: "/login" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const login = useMutation({
    mutationFn: () => call(api.POST("/api/v1/auth/login", { body: { email, password } })),
    onSuccess: async (res) => {
      queryClient.setQueryData(meQuery.queryKey, res.data);
      await navigate({ to: "/dashboard" });
    },
  });

  const errorCode = login.error instanceof ApiError ? login.error.code : urlError;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };

  return (
    <div className="sm-auth">
      <form className="sm-auth-card" onSubmit={submit}>
        <Text tag="h1" size={500} bold>
          Sign in to Brandiz
        </Text>
        {errorCode && <Notice>{MESSAGES[errorCode] ?? "Something went wrong."}</Notice>}
        {errorCode === "email_not_verified" && email && <ResendVerification email={email} />}
        <Button tag="a" href={`${API_BASE}/api/v1/auth/google/login`} use="secondary" size="l">
          Continue with Google
        </Button>
        <div className="sm-or">or</div>
        <label className="sm-field">
          Email
          <Input size="l">
            <Input.Value type="email" value={email} onChange={setEmail} autoComplete="email" />
          </Input>
        </label>
        <label className="sm-field">
          Password
          <Input size="l">
            <Input.Value
              type="password"
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
            />
          </Input>
        </label>
        <Button type="submit" use="primary" size="l" loading={login.isPending}>
          Sign in
        </Button>
        <Text size={200}>
          No account? <Link to="/signup">Create one</Link>
        </Text>
      </form>
    </div>
  );
}
