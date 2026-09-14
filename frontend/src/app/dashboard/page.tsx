"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  getDashboardOverview,
  getFindingsPipeline,
  getPendingApprovals,
  type Approval,
  type DashboardOverview,
  type FindingsPipeline,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";

const SEVERITY_COLORS: Record<string, string> = {
  HIGH: "#dc2626",
  MEDIUM: "#d97706",
  LOW: "#0284c7",
};

const STAGE_LABELS: Record<keyof FindingsPipeline, string> = {
  new_finding: "New finding",
  redline_suggested: "Redline suggested",
  pending_approval: "Pending approval",
  fixed_applied: "Fixed & applied",
  rejected: "Rejected",
};

export default function DashboardPage() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [pipeline, setPipeline] = useState<FindingsPipeline | null>(null);
  const [pending, setPending] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const role = getCurrentUser()?.role;
  const isReviewer = role === "reviewer" || role === "admin";

  useEffect(() => {
    getDashboardOverview().then(setOverview).catch((e) => setError(e.message));
    getFindingsPipeline().then(setPipeline).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!isReviewer) return;
    getPendingApprovals().then(setPending).catch(() => {});
  }, [isReviewer]);

  const severityData = overview
    ? Object.entries(overview.findings_by_severity)
        .filter(([, count]) => count > 0)
        .map(([severity, count]) => ({ name: severity, value: count }))
    : [];

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
      <p className="mt-1 text-sm text-neutral-500">
        A read-only view over what Detect, Suggest, and Fix &amp; Learn have already
        computed — nothing here runs a new analysis.
      </p>

      {error && (
        <p className="mt-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      <section className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded border border-neutral-200 p-4">
          <p className="text-xs font-semibold uppercase text-neutral-500">Contracts</p>
          <p className="mt-1 text-3xl font-semibold">{overview?.total_contracts ?? "—"}</p>
        </div>
        <div className="rounded border border-neutral-200 p-4">
          <p className="text-xs font-semibold uppercase text-neutral-500">Pending approvals</p>
          <p className="mt-1 text-3xl font-semibold">
            {overview?.approvals_by_status.pending ?? "—"}
          </p>
        </div>
        <div className="rounded border border-neutral-200 p-4">
          <p className="text-xs font-semibold uppercase text-neutral-500">Fixed &amp; applied</p>
          <p className="mt-1 text-3xl font-semibold">
            {overview?.approvals_by_status.approved ?? "—"}
          </p>
        </div>
      </section>

      <section className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div className="rounded border border-neutral-200 p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Findings by severity
          </h2>
          {severityData.length === 0 ? (
            <p className="mt-4 text-sm text-neutral-400">No findings yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={severityData} dataKey="value" nameKey="name" outerRadius={80} label>
                  {severityData.map((entry) => (
                    <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name] ?? "#94a3b8"} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="rounded border border-neutral-200 p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Findings pipeline
          </h2>
          {!pipeline ? (
            <p className="mt-4 text-sm text-neutral-400">Loading…</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {(Object.keys(STAGE_LABELS) as (keyof FindingsPipeline)[]).map((stage) => (
                <li key={stage} className="flex items-center justify-between text-sm">
                  <span className="text-neutral-600">{STAGE_LABELS[stage]}</span>
                  <span className="rounded bg-neutral-100 px-2 py-0.5 font-semibold">
                    {pipeline[stage].length}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {isReviewer && (
        <section className="mt-8 rounded border border-amber-300 bg-amber-50 p-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-800">
              Pending approvals ({pending?.length ?? "…"})
            </h2>
            <Link href="/approvals" className="text-xs font-semibold text-sky-700 underline">
              Open Approval Queue →
            </Link>
          </div>
          {pending && pending.length === 0 && (
            <p className="mt-2 text-sm text-amber-700">Nothing waiting on you right now.</p>
          )}
          {pending && pending.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm text-amber-900">
              {pending.slice(0, 5).map((a) => (
                <li key={a.id}>
                  {a.clause_id} — contract {a.contract_id} (confidence {a.confidence})
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
