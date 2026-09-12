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
  finding_id: string | null;
  contract_id: string;
  clause_id: string;
  original_clause_text: string;
  proposed_text: string;
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
  | "abstained";

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
}

export interface ChatSessionInfo {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
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

export interface NotificationInfo {
  id: string;
  finding_id: string;
  severity: Severity;
  message: string;
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
