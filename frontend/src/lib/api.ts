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
