"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  createRestoreRequest,
  downloadDocumentVersion,
  getDetectReport,
  getDocumentVersions,
  type DetectReport,
  type DocumentVersionInfo,
  type Severity,
} from "@/lib/api";

const SEVERITY_STYLES: Record<Severity, string> = {
  HIGH: "border-red-500 bg-red-50 text-red-900",
  MEDIUM: "border-amber-500 bg-amber-50 text-amber-900",
  LOW: "border-sky-500 bg-sky-50 text-sky-900",
};

export default function ContractDetailPage() {
  const params = useParams<{ id: string }>();
  const contractId = params.id;

  const [report, setReport] = useState<DetectReport | null>(null);
  const [versions, setVersions] = useState<DocumentVersionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [r, v] = await Promise.all([
        getDetectReport(contractId),
        getDocumentVersions(contractId),
      ]);
      setReport(r);
      setVersions(v);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contract");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contractId]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  }

  async function onDownload(v: DocumentVersionInfo) {
    try {
      await downloadDocumentVersion(v.id, `${contractId}_v${v.version_number}.docx`);
    } catch (err) {
      showToast(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }

  async function onRequestRestore(v: DocumentVersionInfo) {
    setBusy(true);
    try {
      await createRestoreRequest(contractId, v.id, reason);
      showToast(`Restore requested for v${v.version_number} — a reviewer must approve it.`);
      setRestoringId(null);
      setReason("");
    } catch (err) {
      showToast(`Failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setBusy(false);
    }
  }

  const latestVersionNumber = versions && versions.length > 0
    ? Math.max(...versions.map((v) => v.version_number))
    : null;

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">
        {report?.filename ?? contractId}
      </h1>
      <p className="mt-1 text-xs text-neutral-400">contract {contractId}</p>

      {toast && (
        <p className="mt-4 rounded border border-neutral-300 bg-neutral-50 p-3 text-sm">{toast}</p>
      )}
      {error && (
        <p className="mt-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Current findings ({report?.total_findings ?? "…"})
        </h2>
        {report && report.total_findings === 0 && (
          <p className="mt-3 rounded border border-emerald-400 bg-emerald-50 p-3 text-sm text-emerald-800">
            No compliance issues detected.
          </p>
        )}
        {report && report.total_findings > 0 && (
          <ul className="mt-3 space-y-2">
            {report.findings.map((f) => (
              <li
                key={f.finding_id}
                className={`rounded border-l-4 p-3 text-sm ${SEVERITY_STYLES[f.severity]}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-white/60 px-1.5 py-0.5 text-xs font-semibold">
                    {f.severity}
                  </span>
                  <span className="font-medium">{f.rule_or_regulation_violated}</span>
                  <span className="text-xs opacity-70">page {f.page_number}</span>
                </div>
                <p className="mt-1 opacity-90">{f.explanation}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Version history
        </h2>
        {versions === null ? (
          <p className="mt-3 text-sm text-neutral-500">Loading…</p>
        ) : versions.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">No document versions on file yet.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {versions.map((v) => {
              const isCurrent = v.version_number === latestVersionNumber;
              const isRestoring = restoringId === v.id;
              return (
                <li key={v.id} className="rounded border border-neutral-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">v{v.version_number}</span>
                    {isCurrent && (
                      <span className="rounded bg-neutral-200 px-1.5 py-0.5 text-xs font-semibold">
                        current
                      </span>
                    )}
                    <span className="text-xs text-neutral-400">
                      {new Date(v.created_at).toLocaleString()}
                    </span>
                    <button
                      type="button"
                      onClick={() => onDownload(v)}
                      className="ml-auto text-xs font-semibold text-sky-700 underline"
                    >
                      Download
                    </button>
                    {!isCurrent && !isRestoring && (
                      <button
                        type="button"
                        onClick={() => setRestoringId(v.id)}
                        className="text-xs font-semibold text-amber-700 underline"
                      >
                        Request Restore
                      </button>
                    )}
                  </div>

                  {isRestoring && (
                    <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-2">
                      <p className="text-xs font-semibold uppercase text-amber-700">
                        Why should this version be restored?
                      </p>
                      <textarea
                        className="mt-1 w-full rounded border border-neutral-300 p-2 text-sm"
                        rows={2}
                        placeholder="e.g. The approved edit introduced an error we need to undo."
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                      />
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          disabled={busy || !reason.trim()}
                          onClick={() => onRequestRestore(v)}
                          className="rounded bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                        >
                          {busy ? "Submitting…" : "Submit request"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRestoringId(null);
                            setReason("");
                          }}
                          className="rounded border border-neutral-400 px-3 py-1.5 text-xs font-semibold"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}
