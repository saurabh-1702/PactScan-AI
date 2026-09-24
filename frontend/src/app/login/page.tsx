"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Wordmark } from "@/components/shell/Sidebar";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { login } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await login(email, password);
      setToken(res.access_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="page-in w-full max-w-sm">
        <Wordmark />
        <h1 className="mt-8 text-xl font-semibold tracking-tight text-ink">Sign in</h1>
        <p className="mt-1 text-[13px] text-muted">
          Use your work account to review contracts and compliance findings.
        </p>

        <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
          <Field label="Email">
            {(p) => (
              <Input
                {...p}
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field label="Password">
            {(p) => (
              <Input
                {...p}
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button type="submit" variant="primary" loading={busy} className="mt-1 w-full">
            {busy ? "Signing in" : "Sign in"}
          </Button>
        </form>

        <div className="mt-8 rounded-lg border border-line bg-surface p-4 text-xs text-muted">
          <p className="font-medium text-ink">Demo accounts</p>
          <dl className="mt-2 space-y-1">
            <div className="flex justify-between gap-3">
              <dt>Legal User</dt>
              <dd className="font-mono text-ink">enduser@demo.pactscan.ai</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt>Reviewer</dt>
              <dd className="font-mono text-ink">reviewer@demo.pactscan.ai</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt>Administrator</dt>
              <dd className="font-mono text-ink">admin@demo.pactscan.ai</dd>
            </div>
          </dl>
          <p className="mt-2">
            Password <span className="font-mono text-ink">PactScanDemo123!</span>
          </p>
        </div>
      </div>
    </main>
  );
}
