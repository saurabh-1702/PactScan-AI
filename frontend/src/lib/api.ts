export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

export async function postDetect(file: File): Promise<DetectReport> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE_URL}/api/detect`, {
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
  const res = await fetch(`${API_BASE_URL}/api/suggest/from-finding/${findingId}`, {
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
  const res = await fetch(`${API_BASE_URL}/api/approvals?status=pending`);
  return handleJson<Approval[]>(res);
}

/** All approvals regardless of status — needed so a decided item's document
 * download link stays reachable after it leaves the pending queue. */
export async function getAllApprovals(): Promise<Approval[]> {
  const res = await fetch(`${API_BASE_URL}/api/approvals`);
  return handleJson<Approval[]>(res);
}

export async function decideApproval(
  approvalId: string,
  decision: "approved" | "rejected",
  options?: { note?: string; editedText?: string },
): Promise<Approval> {
  const res = await fetch(`${API_BASE_URL}/api/approvals/${approvalId}/decide`, {
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
  const res = await fetch(`${API_BASE_URL}/api/documents/contract/${contractId}/versions`);
  return handleJson<DocumentVersionInfo[]>(res);
}

export function documentDownloadUrl(versionId: string): string {
  return `${API_BASE_URL}/api/documents/version/${versionId}/download`;
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
  const res = await fetch(`${API_BASE_URL}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  });
  return handleJson<AskApiResponse>(res);
}

export async function getChatSessions(): Promise<ChatSessionInfo[]> {
  const res = await fetch(`${API_BASE_URL}/api/ask/sessions`);
  return handleJson<ChatSessionInfo[]>(res);
}

export async function getChatMessages(sessionId: string): Promise<ChatMessageInfo[]> {
  const res = await fetch(`${API_BASE_URL}/api/ask/sessions/${sessionId}/messages`);
  return handleJson<ChatMessageInfo[]>(res);
}
