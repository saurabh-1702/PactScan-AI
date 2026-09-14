"use client";

import Link from "next/link";
import { useState } from "react";
import { postSimulateRegulationUpdate, type SimulateUpdateResult } from "@/lib/api";

export default function HorizonScanningAdminPage() {
  const [regulationName, setRegulationName] = useState("DPDP Act 2023 (India)");
  const [newClauseText, setNewClauseText] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulateUpdateResult | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await postSimulateRegulationUpdate(regulationName, newClauseText, effectiveDate);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Horizon-Scanning</h1>
      <p className="mt-1 text-sm text-neutral-500">
        Simulate a new or amended regulation clause landing, and re-diff it against every
        clause already in the portfolio — including contracts signed and reviewed long ago.
      </p>
      <p className="mt-3 rounded border border-sky-300 bg-sky-50 p-3 text-xs text-sky-800">
        In production, this runs automatically on a schedule against real regulatory feeds.
        This manual trigger simulates that process for demonstration purposes.
      </p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3">
        <label className="text-sm font-medium">
          Regulation
          <input
            type="text"
            required
            value={regulationName}
            onChange={(e) => setRegulationName(e.target.value)}
            className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm font-medium">
          New / amended clause text
          <textarea
            required
            rows={4}
            value={newClauseText}
            onChange={(e) => setNewClauseText(e.target.value)}
            placeholder="e.g. Data Fiduciaries must obtain verifiable parental consent before processing a child's personal data..."
            className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm font-medium">
          Effective date
          <input
            type="date"
            required
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
            className="mt-1 w-full rounded border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Scanning…" : "Simulate update & re-scan portfolio"}
        </button>
      </form>

      {error && (
        <p className="mt-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {result && (
        <section className="mt-8">
          <h2 className="text-lg font-medium">
            {result.contracts_flagged} contract{result.contracts_flagged === 1 ? "" : "s"} newly
            flagged ({result.findings_created} new finding
            {result.findings_created === 1 ? "" : "s"})
          </h2>
          {result.contracts_flagged === 0 ? (
            <p className="mt-3 rounded border border-emerald-400 bg-emerald-50 p-3 text-sm text-emerald-800">
              No existing contract was affected by this update.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {result.details.map((d) => (
                <li key={d.contract_id} className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">
                  <Link
                    href={`/contracts/${d.contract_id}`}
                    className="font-semibold text-sky-700 underline"
                  >
                    {d.filename}
                  </Link>
                  <span className="ml-2 text-xs text-neutral-600">
                    {d.new_finding_ids.length} new finding{d.new_finding_ids.length === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
