import Button from "@semcore/ui/button";
import Input from "@semcore/ui/input";
import Notice from "@semcore/ui/notice";
import { Text } from "@semcore/ui/typography";
import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { API_BASE, ApiError, api, call } from "../api/client";
import { ResendVerification } from "../components/ResendVerification";

export function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const signup = useMutation({
    mutationFn: () =>
      call(api.POST("/api/v1/auth/signup", { body: { email, password, name: name || null } })),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    signup.mutate();
  };

  if (signup.isSuccess) {
    return (
      <div className="sm-auth">
        <div className="sm-auth-card">
          <Text tag="h1" size={500} bold>
            Check your inbox
          </Text>
          <Text>
            We sent a verification link to <b>{signup.data.data.email}</b>. Open it to finish
            creating your account. The link expires in 48 hours.
          </Text>
          <ResendVerification email={signup.data.data.email} />
          <Link to="/login" search={{ error: undefined }}>
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  const error =
    signup.error instanceof ApiError
      ? signup.error.code === "email_taken"
        ? "An account with this email already exists."
        : signup.error.code === "validation_error"
          ? "Use a valid email and a password of at least 10 characters."
          : signup.error.message
      : null;

  return (
    <div className="sm-auth">
      <form className="sm-auth-card" onSubmit={submit}>
        <Text tag="h1" size={500} bold>
          Create your Brandiz account
        </Text>
        {error && <Notice>{error}</Notice>}
        <Button tag="a" href={`${API_BASE}/api/v1/auth/google/login`} use="secondary" size="l">
          Sign up with Google
        </Button>
        <div className="sm-or">or</div>
        <label className="sm-field">
          Name
          <Input size="l">
            <Input.Value value={name} onChange={setName} autoComplete="name" />
          </Input>
        </label>
        <label className="sm-field">
          Email
          <Input size="l">
            <Input.Value type="email" value={email} onChange={setEmail} autoComplete="email" />
          </Input>
        </label>
        <label className="sm-field">
          Password (10+ characters)
          <Input size="l">
            <Input.Value
              type="password"
              value={password}
              onChange={setPassword}
              autoComplete="new-password"
            />
          </Input>
        </label>
        <Button type="submit" use="primary" size="l" loading={signup.isPending}>
          Create account
        </Button>
        <Text size={200}>
          Have an account?{" "}
          <Link to="/login" search={{ error: undefined }}>
            Sign in
          </Link>
        </Text>
      </form>
    </div>
  );
}
