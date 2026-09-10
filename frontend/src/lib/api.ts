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

export async function postDetect(file: File): Promise<DetectReport> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE_URL}/api/detect`, {
    method: "POST",
    body: form,
  });
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
