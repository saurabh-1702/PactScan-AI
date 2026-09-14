"use client";

import { useEffect, useState } from "react";
import {
  decideApproval,
  decideRestoreRequest,
  downloadDocumentVersion,
  getAllApprovals,
  getDocumentVersions,
  getRestoreRequests,
  type Approval,
  type DocumentVersionInfo,
  type RestoreRequestInfo,
} from "@/lib/api";

const STATUS_STYLES: Record<Approval["status"], string> = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-800",
};

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editedText, setEditedText] = useState<Record<string, string>>({});
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectNote, setRejectNote] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<string | null>(null);
  const [versionsByContract, setVersionsByContract] = useState<
    Record<string, DocumentVersionInfo[]>
  >({});

  const [restoreRequests, setRestoreRequests] = useState<RestoreRequestInfo[] | null>(null);
  const [restoreBusyId, setRestoreBusyId] = useState<string | null>(null);
  const [restoreRejectingId, setRestoreRejectingId] = useState<string | null>(null);
  const [restoreRejectNote, setRestoreRejectNote] = useState<Record<string, string>>({});

  async function load() {
    try {
      // fetch ALL approvals, not just pending — a decided item's download link
      // must stay reachable after it leaves the pending queue.
      const list = await getAllApprovals();
      setApprovals(list);
      const contractIds = [...new Set(list.map((a) => a.contract_id))];
      for (const cid of contractIds) {
        getDocumentVersions(cid)
          .then((versions) => setVersionsByContract((prev) => ({ ...prev, [cid]: versions })))
          .catch(() => {});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load approvals");
    }
    try {
      const restores = await getRestoreRequests();
      setRestoreRequests(restores);
      const restoreContractIds = [...new Set(restores.map((r) => r.contract_id))];
      for (const cid of restoreContractIds) {
        getDocumentVersions(cid)
          .then((versions) => setVersionsByContract((prev) => ({ ...prev, [cid]: versions })))
          .catch(() => {});
      }
    } catch {
      /* non-fatal — restore section just stays empty */
    }
  }

  useEffect(() => {
    load();
  }, []);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  }

  async function onDownload(versionId: string, contractId: string, versionNumber: number) {
    try {
      await downloadDocumentVersion(versionId, `${contractId}_v${versionNumber}.docx`);
    } catch (err) {
      showToast(`Download failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }

  async function onDecide(
    a: Approval,
    decision: "approved" | "rejected",
    useEdit: boolean,
    note?: string,
  ) {
    setBusyId(a.id);
    try {
      await decideApproval(a.id, decision, {
        editedText: useEdit ? editedText[a.id] : undefined,
        note,
      });
      showToast(
        decision === "approved"
          ? `Approved — the redline was written into a new document version.`
          : `Rejected — the requester will see your note, and no file was touched.`,
      );
      setEditingId(null);
      setRejectingId(null);
      await load();
    } catch (err) {
      showToast(`Failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setBusyId(null);
    }
  }

  async function onDecideRestore(
    r: RestoreRequestInfo,
    decision: "approved" | "rejected",
    note?: string,
  ) {
    setRestoreBusyId(r.id);
    try {
      await decideRestoreRequest(r.id, decision, note);
      showToast(
        decision === "approved"
          ? `Approved — the target version was copied forward as a new version.`
          : `Rejected — the requester will see your note.`,
      );
      setRestoreRejectingId(null);
      await load();
    } catch (err) {
      showToast(`Failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setRestoreBusyId(null);
    }
  }

  const pending = (approvals ?? []).filter((a) => a.status === "pending");
  const decided = (approvals ?? [])
    .filter((a) => a.status !== "pending")
    .sort((a, b) => (b.decided_at ?? "").localeCompare(a.decided_at ?? ""));

  const pendingRestores = (restoreRequests ?? []).filter((r) => r.status === "pending");
  const decidedRestores = (restoreRequests ?? [])
    .filter((r) => r.status !== "pending")
    .sort((a, b) => (b.decided_at ?? "").localeCompare(a.decided_at ?? ""));

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">
        PactScan AI — Approval Queue
      </h1>
      <p className="mt-1 text-sm text-neutral-500">
        Every Suggest output lands here as a pending approval. Nothing is ever
        written into a real document until you explicitly decide it here.
      </p>

      {toast && (
        <p className="mt-4 rounded border border-neutral-300 bg-neutral-50 p-3 text-sm">
          {toast}
        </p>
      )}
      {error && (
        <p className="mt-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {approvals === null ? (
        <p className="mt-6 text-sm text-neutral-500">Loading…</p>
      ) : (
        <>
          <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Pending ({pending.length})
          </h2>
          {pending.length === 0 ? (
            <p className="mt-3 rounded border border-neutral-300 bg-neutral-50 p-3 text-sm text-neutral-600">
              No pending approvals.
            </p>
          ) : (
            <ul className="mt-3 space-y-4">
              {pending.map((a) => {
                const isEditing = editingId === a.id;
                const isRejecting = rejectingId === a.id;
                const isBusy = busyId === a.id;
                const versions = versionsByContract[a.contract_id] ?? [];
                const latest = versions[versions.length - 1];

                return (
                  <li key={a.id} className="rounded border border-neutral-300 p-4 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">{a.clause_id}</span>
                      <span className="text-xs text-neutral-400">
                        contract {a.contract_id} · confidence {a.confidence}
                      </span>
                    </div>

                    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="rounded border border-red-300 bg-red-50 p-2">
                        <p className="text-xs font-semibold uppercase text-red-700">Original</p>
                        <p className="mt-1 whitespace-pre-wrap">{a.original_clause_text}</p>
                      </div>
                      <div className="rounded border border-emerald-300 bg-emerald-50 p-2">
                        <p className="text-xs font-semibold uppercase text-emerald-700">
                          Proposed
                        </p>
                        {isEditing ? (
                          <textarea
                            className="mt-1 w-full rounded border border-neutral-300 p-2 text-sm"
                            rows={5}
                            value={editedText[a.id] ?? a.proposed_text}
                            onChange={(e) =>
                              setEditedText((prev) => ({ ...prev, [a.id]: e.target.value }))
                            }
                          />
                        ) : (
                          <p className="mt-1 whitespace-pre-wrap">{a.proposed_text}</p>
                        )}
                      </div>
                    </div>

                    <p className="mt-2 text-xs text-neutral-600">
                      <span className="font-semibold">Rationale: </span>
                      {a.rationale}
                    </p>

                    {isRejecting && (
                      <div className="mt-3 rounded border border-red-300 bg-red-50 p-2">
                        <p className="text-xs font-semibold uppercase text-red-700">
                          Reason for rejection (shown to whoever requested this fix)
                        </p>
                        <textarea
                          className="mt-1 w-full rounded border border-neutral-300 p-2 text-sm"
                          rows={3}
                          placeholder="e.g. This cap is still too low for our risk tolerance."
                          value={rejectNote[a.id] ?? ""}
                          onChange={(e) =>
                            setRejectNote((prev) => ({ ...prev, [a.id]: e.target.value }))
                          }
                        />
                      </div>
                    )}

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {!isEditing && !isRejecting && (
                        <>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => onDecide(a, "approved", false)}
                            className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            {isBusy ? "Working…" : "Accept"}
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => setRejectingId(a.id)}
                            className="rounded bg-red-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => {
                              setEditingId(a.id);
                              setEditedText((prev) => ({ ...prev, [a.id]: a.proposed_text }));
                            }}
                            className="rounded border border-neutral-400 px-3 py-1.5 text-xs font-semibold disabled:opacity-40"
                          >
                            Edit
                          </button>
                        </>
                      )}
                      {isEditing && (
                        <>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => onDecide(a, "approved", true)}
                            className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            {isBusy ? "Working…" : "Approve edited"}
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => setEditingId(null)}
                            className="rounded border border-neutral-400 px-3 py-1.5 text-xs font-semibold"
                          >
                            Cancel
                          </button>
                        </>
                      )}
                      {isRejecting && (
                        <>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => onDecide(a, "rejected", false, rejectNote[a.id])}
                            className="rounded bg-red-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            {isBusy ? "Working…" : "Confirm reject"}
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => setRejectingId(null)}
                            className="rounded border border-neutral-400 px-3 py-1.5 text-xs font-semibold"
                          >
                            Cancel
                          </button>
                        </>
                      )}

                      {latest && (
                        <button
                          type="button"
                          onClick={() => onDownload(latest.id, a.contract_id, latest.version_number)}
                          className="ml-auto text-xs font-semibold text-sky-700 underline"
                        >
                          Download latest document (v{latest.version_number})
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Decided ({decided.length})
          </h2>
          {decided.length === 0 ? (
            <p className="mt-3 text-sm text-neutral-500">Nothing decided yet.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {decided.map((a) => {
                const versions = versionsByContract[a.contract_id] ?? [];
                const latest = versions[versions.length - 1];
                return (
                  <li
                    key={a.id}
                    className="rounded border border-neutral-200 p-3 text-sm text-neutral-700"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${STATUS_STYLES[a.status]}`}
                      >
                        {a.status}
                      </span>
                      <span className="font-medium">{a.clause_id}</span>
                      <span className="text-xs text-neutral-400">
                        contract {a.contract_id} · decided{" "}
                        {a.decided_at ? new Date(a.decided_at).toLocaleString() : "—"}
                      </span>
                      {a.status === "approved" && latest && (
                        <button
                          type="button"
                          onClick={() => onDownload(latest.id, a.contract_id, latest.version_number)}
                          className="ml-auto text-xs font-semibold text-sky-700 underline"
                        >
                          Download document (v{latest.version_number})
                        </button>
                      )}
                    </div>
                    {a.reviewer_note && (
                      <p className="mt-1 text-xs italic text-neutral-500">
                        Note: {a.reviewer_note}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Restore requests — pending ({pendingRestores.length})
          </h2>
          {pendingRestores.length === 0 ? (
            <p className="mt-3 rounded border border-neutral-300 bg-neutral-50 p-3 text-sm text-neutral-600">
              No pending restore requests.
            </p>
          ) : (
            <ul className="mt-3 space-y-4">
              {pendingRestores.map((r) => {
                const isBusy = restoreBusyId === r.id;
                const isRejecting = restoreRejectingId === r.id;
                return (
                  <li key={r.id} className="rounded border border-neutral-300 p-4 text-sm">
                    {r.abuse_flagged && (
                      <p className="mb-2 rounded border border-red-400 bg-red-50 p-2 text-xs font-semibold text-red-800">
                        ⚠ This contract has had multiple restores approved recently — review this
                        request carefully before approving another.
                      </p>
                    )}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">
                        Restore to v{r.target_version_number}
                      </span>
                      <span className="text-xs text-neutral-400">
                        contract {r.contract_id} · requested{" "}
                        {new Date(r.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-neutral-600">
                      <span className="font-semibold">Reason: </span>
                      {r.reason}
                    </p>

                    {isRejecting && (
                      <div className="mt-3 rounded border border-red-300 bg-red-50 p-2">
                        <p className="text-xs font-semibold uppercase text-red-700">
                          Reason for rejection (shown to the requester)
                        </p>
                        <textarea
                          className="mt-1 w-full rounded border border-neutral-300 p-2 text-sm"
                          rows={2}
                          value={restoreRejectNote[r.id] ?? ""}
                          onChange={(e) =>
                            setRestoreRejectNote((prev) => ({ ...prev, [r.id]: e.target.value }))
                          }
                        />
                      </div>
                    )}

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {!isRejecting ? (
                        <>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => onDecideRestore(r, "approved")}
                            className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            {isBusy ? "Working…" : "Accept"}
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => setRestoreRejectingId(r.id)}
                            className="rounded bg-red-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            Reject
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => onDecideRestore(r, "rejected", restoreRejectNote[r.id])}
                            className="rounded bg-red-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                          >
                            {isBusy ? "Working…" : "Confirm reject"}
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => setRestoreRejectingId(null)}
                            className="rounded border border-neutral-400 px-3 py-1.5 text-xs font-semibold"
                          >
                            Cancel
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Restore requests — decided ({decidedRestores.length})
          </h2>
          {decidedRestores.length === 0 ? (
            <p className="mt-3 text-sm text-neutral-500">Nothing decided yet.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {decidedRestores.map((r) => {
                const versions = versionsByContract[r.contract_id] ?? [];
                const latest = versions[versions.length - 1];
                return (
                  <li key={r.id} className="rounded border border-neutral-200 p-3 text-sm text-neutral-700">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${STATUS_STYLES[r.status]}`}
                      >
                        {r.status}
                      </span>
                      <span className="font-medium">Restore to v{r.target_version_number}</span>
                      <span className="text-xs text-neutral-400">
                        contract {r.contract_id} · decided{" "}
                        {r.decided_at ? new Date(r.decided_at).toLocaleString() : "—"}
                      </span>
                      {r.status === "approved" && latest && (
                        <button
                          type="button"
                          onClick={() => onDownload(latest.id, r.contract_id, latest.version_number)}
                          className="ml-auto text-xs font-semibold text-sky-700 underline"
                        >
                          Download document (v{latest.version_number})
                        </button>
                      )}
                    </div>
                    {r.reviewer_note && (
                      <p className="mt-1 text-xs italic text-neutral-500">Note: {r.reviewer_note}</p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
