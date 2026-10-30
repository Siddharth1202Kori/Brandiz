import Button from "@semcore/ui/button";
import { Text } from "@semcore/ui/typography";
import { useMutation } from "@tanstack/react-query";

import { ApiError, api, call } from "../api/client";

/** Re-sends the verification email. The API answers the same whether or not the account exists. */
export function ResendVerification({ email }: { email: string }) {
  const resend = useMutation({
    mutationFn: () => call(api.POST("/api/v1/auth/resend-verification", { body: { email } })),
  });

  if (resend.isSuccess) {
    return <Text size={200}>If that account needs verifying, a new link is on its way.</Text>;
  }
  return (
    <>
      <Button use="tertiary" onClick={() => resend.mutate()} loading={resend.isPending}>
        Resend verification email
      </Button>
      {resend.error instanceof ApiError && resend.error.code === "rate_limited" && (
        <Text size={200}>Too many requests. Try again in a few minutes.</Text>
      )}
    </>
  );
}
