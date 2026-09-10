"use client";

import { useState } from "react";
import { postDetect, type DetectReport, type Severity } from "@/lib/api";

const SEVERITY_STYLES: Record<Severity, string> = {
  HIGH: "border-red-500 bg-red-50 text-red-900",
  MEDIUM: "border-amber-500 bg-amber-50 text-amber-900",
  LOW: "border-sky-500 bg-sky-50 text-sky-900",
};

export default function DetectPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<DetectReport | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      setReport(await postDetect(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">
        PactScan AI — Detect
      </h1>
      <p className="mt-1 text-sm text-neutral-500">
        Upload a vendor DPA / MSA. Detect parses it, maps it into the knowledge
        graph, and checks it against the playbook + DPDP / GDPR.
      </p>

      <form onSubmit={onSubmit} className="mt-6 flex items-center gap-3">
        <input
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        <button
          type="submit"
          disabled={!file || loading}
          className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Analysing…" : "Run Detect"}
        </button>
      </form>

      {error && (
        <p className="mt-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {report && (
        <section className="mt-8">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-medium">
              {report.total_findings} finding
              {report.total_findings === 1 ? "" : "s"}
            </h2>
            <span className="text-xs text-neutral-400">
              contract {report.contract_id}
            </span>
          </div>

          {report.total_findings === 0 ? (
            <p className="mt-3 rounded border border-emerald-400 bg-emerald-50 p-3 text-sm text-emerald-800">
              No compliance issues detected.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {report.findings.map((f) => (
                <li
                  key={f.finding_id}
                  className={`rounded border-l-4 p-3 text-sm ${SEVERITY_STYLES[f.severity]}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-white/60 px-1.5 py-0.5 text-xs font-semibold">
                      {f.severity}
                    </span>
                    <span className="font-medium">{f.clause_type}</span>
                    <span className="text-xs opacity-70">
                      page {f.page_number} · {f.section_header}
                    </span>
                    {f.override_chain.length > 1 && (
                      <span className="rounded bg-white/60 px-1.5 py-0.5 text-xs font-semibold">
                        multi-hop override ({f.override_chain.length} clauses)
                      </span>
                    )}
                  </div>
                  <p className="mt-1 font-medium">
                    {f.rule_or_regulation_violated}
                  </p>
                  <p className="mt-1 opacity-90">{f.explanation}</p>
                  <p className="mt-1 text-xs opacity-60">
                    confidence: {f.confidence}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
