"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
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
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-2xl font-semibold tracking-tight">PactScan AI</h1>
      <p className="mt-1 text-sm text-neutral-500">Sign in to continue.</p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3">
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-neutral-300 px-3 py-2 text-sm"
        />
        <input
          type="password"
          required
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-neutral-300 px-3 py-2 text-sm"
        />
        {error && (
          <p className="rounded border border-red-400 bg-red-50 p-2 text-xs text-red-800">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <div className="mt-6 rounded border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-500">
        <p className="font-semibold text-neutral-600">Demo accounts</p>
        <p className="mt-1">enduser@demo.pactscan.ai — end_user</p>
        <p>reviewer@demo.pactscan.ai — reviewer</p>
        <p className="mt-1">Password: PactScanDemo123!</p>
      </div>
    </main>
  );
}
