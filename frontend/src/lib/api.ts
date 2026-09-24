import { clearToken, getToken } from "@/lib/auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Attaches the stored JWT (if any) to every API call. On a 401, the token is
 * gone/expired — clear it and bounce to /login rather than surfacing a
 * confusing "Request failed (401)" error on whatever page the user was on. */
async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    clearToken();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
  return res;
}

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

// --- Auth (Phase 5) ------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  token_type: string;
  tenant_id: string;
  role: "end_user" | "reviewer" | "admin";
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleJson<LoginResponse>(res);
}

export type Severity = "HIGH" | "MEDIUM" | "LOW";

export interface Finding {
  finding_id: string;
  clause_id: string;
  clause_type: string;
  page_number: number;
  section_header: string;
  severity: Severity;
  rule_or_regulation_violated: string;
  explanation: string;
  confidence: "high" | "medium" | "low";
  override_chain: string[];
}

export interface DetectReport {
  contract_id: string;
  filename: string;
  findings: Finding[];
  total_findings: number;
  timestamp: string | null;
}

export async function postDetect(file: File): Promise<DetectReport> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch("/api/detect", {
    method: "POST",
    body: form,
  });
  return handleJson<DetectReport>(res);
}

export async function getDetectReport(contractId: string): Promise<DetectReport> {
  const res = await authFetch(`/api/detect/${contractId}`);
  return handleJson<DetectReport>(res);
}

// --- Suggest (Phase 2) ------------------------------------------------

export interface ContrarianArgument {
  argument: string;
  strongest_point: string;
  confidence: number;
}

export interface JudgeVerdict {
  verdict: "confirmed" | "downgraded" | "dismissed";
  final_confidence: number;
  reasoning: string;
}

export interface NegotiationFallback {
  predicted_pushback: string;
  fallback_clause_text: string;
}

export interface SuggestResult {
  suggestion_id: string;
  finding_id: string | null;
  contract_id: string;
  clause_id: string;
  proposed_text: string;
  rationale: string;
  confidence: number;
  contrarian: ContrarianArgument | null;
  judge: JudgeVerdict | null;
  negotiation: NegotiationFallback | null;
  created_at: string;
  /** null while it's only a draft — set once the requester submits it */
  approval_id: string | null;
}

export async function postSuggestFromFinding(findingId: string): Promise<SuggestResult> {
  const res = await authFetch(`/api/suggest/from-finding/${findingId}`, {
    method: "POST",
  });
  return handleJson<SuggestResult>(res);
}

// --- Approvals / Fix & Learn (Phase 3) ---------------------------------

export interface Approval {
  id: string;
  redline_suggestion_id: string;
  status: "pending" | "approved" | "rejected";
  reviewer_note: string | null;
  edited_text: string | null;
  decided_at: string | null;
  created_at: string;
  requested_by_user_id: string | null;
  requested_by_email: string | null;
  finding_id: string | null;
  contract_id: string;
  clause_id: string;
  original_clause_text: string;
  /** what was submitted for review: the requester's edit if they made one, else the AI draft */
  proposed_text: string;
  ai_draft_text: string | null;
  requester_edited_text: string | null;
  rationale: string;
  confidence: number;
}

export interface DocumentVersionInfo {
  id: string;
  contract_id: string;
  version_number: number;
  approval_id: string | null;
  created_at: string;
}

export async function getPendingApprovals(): Promise<Approval[]> {
  const res = await authFetch("/api/approvals?status=pending");
  return handleJson<Approval[]>(res);
}

/** All approvals regardless of status — needed so a decided item's document
 * download link stays reachable after it leaves the pending queue. */
export async function getAllApprovals(): Promise<Approval[]> {
  const res = await authFetch("/api/approvals");
  return handleJson<Approval[]>(res);
}

export async function decideApproval(
  approvalId: string,
  decision: "approved" | "rejected",
  options?: { note?: string; editedText?: string },
): Promise<Approval> {
  const res = await authFetch(`/api/approvals/${approvalId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision,
      note: options?.note ?? null,
      edited_text: options?.editedText ?? null,
    }),
  });
  return handleJson<Approval>(res);
}

export async function getDocumentVersions(contractId: string): Promise<DocumentVersionInfo[]> {
  const res = await authFetch(`/api/documents/contract/${contractId}/versions`);
  return handleJson<DocumentVersionInfo[]>(res);
}

/** Downloads now require a Bearer token, which a plain `<a href>` can't send
 * — fetch the file with auth, then hand the browser a local blob URL to save.
 * `revokeObjectURL` is deferred so the click has time to actually start the
 * download. */
export async function downloadDocumentVersion(
  versionId: string,
  filename: string,
): Promise<void> {
  const res = await authFetch(`/api/documents/version/${versionId}/download`);
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// --- Ask agent (Phase 4) ------------------------------------------------

export type AskResponseType =
  | "contract_answer"
  | "status_answer"
  | "edit_draft"
  | "general_info"
  | "out_of_scope"
  | "abstained"
  | "rate_limited"
  | "file_attached";

export interface AskSourceInfo {
  document_name: string;
  page_number: number;
}

export interface AskApiResponse {
  session_id: string;
  type: AskResponseType;
  answer_text: string;
  sources: AskSourceInfo[];
  suggestion_id: string | null;
  approval_id: string | null;
  /** set for file_attached: the contract the attached file became */
  contract_id: string | null;
}

export interface ChatSessionInfo {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  active_contract_id: string | null;
  active_filename: string | null;
}

export interface ChatMessageInfo {
  id: string;
  role: "user" | "assistant";
  content: string;
  response_type: AskResponseType | null;
  sources: AskSourceInfo[];
  suggestion_id: string | null;
  approval_id: string | null;
  created_at: string;
}

export async function postAsk(message: string, sessionId?: string | null): Promise<AskApiResponse> {
  const res = await authFetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  });
  return handleJson<AskApiResponse>(res);
}

export async function getChatSessions(): Promise<ChatSessionInfo[]> {
  const res = await authFetch("/api/ask/sessions");
  return handleJson<ChatSessionInfo[]>(res);
}

export async function getChatMessages(sessionId: string): Promise<ChatMessageInfo[]> {
  const res = await authFetch(`/api/ask/sessions/${sessionId}/messages`);
  return handleJson<ChatMessageInfo[]>(res);
}

// --- Notifications (Phase 5) ---------------------------------------------

export type NotificationKind = "new_finding" | "approval_decided";

export interface NotificationInfo {
  id: string;
  kind: NotificationKind;
  finding_id: string | null;
  severity: Severity | null;
  message: string;
  document_version_id: string | null;
  is_read: boolean;
  created_at: string;
}

export async function getNotifications(unreadOnly = false): Promise<NotificationInfo[]> {
  const res = await authFetch(`/api/notifications?unread_only=${unreadOnly}`);
  return handleJson<NotificationInfo[]>(res);
}

export async function markNotificationRead(id: string): Promise<NotificationInfo> {
  const res = await authFetch(`/api/notifications/${id}/mark-read`, { method: "POST" });
  return handleJson<NotificationInfo>(res);
}

// --- Dashboard (Phase 5) ---------------------------------------------------

export interface DashboardOverview {
  total_contracts: number;
  findings_by_severity: Record<Severity, number>;
  approvals_by_status: Record<"pending" | "approved" | "rejected", number>;
}

export interface PipelineFinding {
  finding_id: string;
  contract_id: string;
  severity: Severity;
  rule_or_regulation_violated: string;
}

export interface FindingsPipeline {
  new_finding: PipelineFinding[];
  redline_suggested: PipelineFinding[];
  pending_approval: PipelineFinding[];
  fixed_applied: PipelineFinding[];
  rejected: PipelineFinding[];
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const res = await authFetch("/api/dashboard/overview");
  return handleJson<DashboardOverview>(res);
}

export async function getFindingsPipeline(): Promise<FindingsPipeline> {
  const res = await authFetch("/api/dashboard/findings-pipeline");
  return handleJson<FindingsPipeline>(res);
}

// --- Horizon-Scanning (Phase 6, admin-only) --------------------------------

export interface AffectedContract {
  contract_id: string;
  filename: string;
  new_finding_ids: string[];
}

export interface SimulateUpdateResult {
  regulation_clause_id: string;
  contracts_flagged: number;
  findings_created: number;
  details: AffectedContract[];
}

export async function postSimulateRegulationUpdate(
  regulationName: string,
  newClauseText: string,
  effectiveDate: string,
): Promise<SimulateUpdateResult> {
  const res = await authFetch("/api/horizon-scanning/simulate-update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      regulation_name: regulationName,
      new_clause_text: newClauseText,
      effective_date: effectiveDate,
    }),
  });
  return handleJson<SimulateUpdateResult>(res);
}

// --- Document Restore (Phase 6) --------------------------------------------

export interface RestoreRequestInfo {
  id: string;
  contract_id: string;
  target_version_id: string;
  target_version_number: number;
  requested_by_user_id: string;
  requested_by_email: string | null;
  reason: string;
  status: "pending" | "approved" | "rejected";
  reviewer_note: string | null;
  abuse_flagged: boolean;
  decided_at: string | null;
  created_at: string;
}

export async function createRestoreRequest(
  contractId: string,
  targetVersionId: string,
  reason: string,
): Promise<RestoreRequestInfo> {
  const res = await authFetch("/api/restore-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id: contractId, target_version_id: targetVersionId, reason }),
  });
  return handleJson<RestoreRequestInfo>(res);
}

export async function getRestoreRequests(status?: string): Promise<RestoreRequestInfo[]> {
  const qs = status ? `?status=${status}` : "";
  const res = await authFetch(`/api/restore-requests${qs}`);
  return handleJson<RestoreRequestInfo[]>(res);
}

export async function decideRestoreRequest(
  id: string,
  decision: "approved" | "rejected",
  note?: string,
): Promise<RestoreRequestInfo> {
  const res = await authFetch(`/api/restore-requests/${id}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note: note ?? null }),
  });
  return handleJson<RestoreRequestInfo>(res);
}

// --- My drafts (Phase 6b) ----------------------------------------------------

export type DraftStatus = "draft" | "pending" | "approved" | "rejected";

/** One suggestion with every text that can exist for it: the AI's draft, the
 * requester's own edit of it, and the reviewer's edit at decision time. */
export interface DraftInfo {
  suggestion_id: string;
  contract_id: string;
  filename: string | null;
  clause_id: string;
  finding_id: string | null;
  original_clause_text: string;
  ai_draft_text: string;
  requester_edited_text: string | null;
  rationale: string;
  confidence: number;
  status: DraftStatus;
  approval_id: string | null;
  reviewer_edited_text: string | null;
  reviewer_note: string | null;
  document_version_id: string | null;
  created_at: string;
  submitted_at: string | null;
  decided_at: string | null;
}

export async function getMyDrafts(): Promise<DraftInfo[]> {
  const res = await authFetch("/api/my-drafts");
  return handleJson<DraftInfo[]>(res);
}

export async function getMyDraft(suggestionId: string): Promise<DraftInfo> {
  const res = await authFetch(`/api/my-drafts/${suggestionId}`);
  return handleJson<DraftInfo>(res);
}

/** Submits a draft to a reviewer. Omit `editedText` (or leave it identical to
 * the AI draft) to submit the AI draft as-is. */
export async function submitDraft(suggestionId: string, editedText?: string): Promise<DraftInfo> {
  const res = await authFetch(`/api/my-drafts/${suggestionId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edited_text: editedText ?? null }),
  });
  return handleJson<DraftInfo>(res);
}

/** Attach a contract to an Ask conversation. This is a real upload — the full
 * Detect pipeline runs on it (so it can take a while) — and the file becomes
 * the conversation's active document. */
export async function postAskAttach(file: File, sessionId?: string | null): Promise<AskApiResponse> {
  const form = new FormData();
  form.append("file", file);
  if (sessionId) form.append("session_id", sessionId);
  const res = await authFetch("/api/ask/attach", { method: "POST", body: form });
  return handleJson<AskApiResponse>(res);
}

export async function clearActiveDocument(sessionId: string): Promise<void> {
  const res = await authFetch(`/api/ask/sessions/${sessionId}/active-document`, {
    method: "DELETE",
  });
  await handleJson<unknown>(res);
}
