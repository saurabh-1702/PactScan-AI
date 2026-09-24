"use client";

import Link from "next/link";
import { Radar, Play } from "lucide-react";
import { useState } from "react";
import { useProcesses } from "@/components/shell/Processes";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert, Badge, EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { Page, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { Table, Td, Th, THead, Tr } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import {
  getRegulationUpdates,
  postSimulateRegulationUpdate,
  type RegulationUpdate,
  type SimulateUpdateResult,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks";
import { useSession } from "@/lib/session";

function UpdateRows({ rows }: { rows: RegulationUpdate[] }) {
  return (
    <Table caption="Regulatory updates">
      <THead>
        <tr>
          <Th>Regulation</Th>
          <Th>Jurisdiction</Th>
          <Th>Effective</Th>
          <Th>Contracts affected</Th>
        </tr>
      </THead>
      <tbody>
        {rows.map((u) => (
          <Tr key={u.id}>
            <Td className="max-w-md">
              <span className="font-medium">{u.regulation_name}</span>
              <span className="block text-xs text-muted">{u.section}</span>
              <details className="mt-1.5">
                <summary className="cursor-pointer text-xs font-medium text-accent">Show clause text</summary>
                <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">{u.text}</p>
              </details>
            </Td>
            <Td muted>{u.jurisdiction ?? "—"}</Td>
            <Td muted>{formatDate(u.effective_date)}</Td>
            <Td>
              {u.kind === "baseline" ? (
                <span className="text-muted">—</span>
              ) : u.affected_contracts.length === 0 ? (
                <span className="text-muted">None</span>
              ) : (
                <ul className="space-y-0.5">
                  {u.affected_contracts.map((c) => (
                    <li key={c.contract_id}>
                      <Link
                        href={`/contracts/${c.contract_id}`}
                        className="font-medium text-accent hover:underline"
                      >
                        {c.filename}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function HorizonScanningPage() {
  const { can } = useSession();
  const updates = useLoad(getRegulationUpdates);
  const [open, setOpen] = useState(false);

  const amendments = (updates.data ?? []).filter((u) => u.kind === "update");
  const baseline = (updates.data ?? []).filter((u) => u.kind === "baseline");

  return (
    <Page>
      <PageHeader
        title="Horizon Scanning"
        description="When a regulation changes, PactScan re-checks the contracts you already have against it, so a contract signed long ago isn't left behind."
        actions={
          can("horizon.trigger") && (
            <Button variant="primary" onClick={() => setOpen(true)}>
              <Play className="h-3.5 w-3.5" aria-hidden /> Simulate an update
            </Button>
          )
        }
      />

      <Alert tone="info" title="Simulated in this build" className="mb-6">
        In production this runs on a schedule against real regulatory feeds. Here, an administrator
        triggers it by hand to demonstrate the same re-check.
      </Alert>

      {updates.error && !updates.data && <Alert tone="danger">{updates.error}</Alert>}

      <section>
        <SectionTitle>Updates</SectionTitle>
        {updates.loading && !updates.data ? (
          <Skeleton className="h-40" />
        ) : amendments.length === 0 ? (
          <EmptyState icon={Radar} title="No regulatory updates yet">
            {can("horizon.trigger")
              ? "Simulate an update to see which of your contracts it affects."
              : "When an administrator records a change to a regulation, it will appear here with the contracts it affects."}
          </EmptyState>
        ) : (
          <UpdateRows rows={amendments} />
        )}
      </section>

      {baseline.length > 0 && (
        <details className="mt-8">
          <summary className="cursor-pointer text-[13px] font-medium text-ink">
            Baseline regulation clauses ({baseline.length})
          </summary>
          <div className="mt-3">
            <UpdateRows rows={baseline} />
          </div>
        </details>
      )}

      {can("horizon.trigger") && (
        <SimulateDialog
          open={open}
          onOpenChange={setOpen}
          onDone={() => updates.reload()}
        />
      )}
    </Page>
  );
}

function SimulateDialog({
  open,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const { track } = useProcesses();
  const [regulation, setRegulation] = useState("DPDP Act 2023 (India)");
  const [text, setText] = useState("");
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulateUpdateResult | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await track(
        "Re-checking contracts against a regulation update",
        postSimulateRegulationUpdate(regulation, text, date),
      );
      setResult(res);
      onDone();
      toast.success(
        res.contracts_flagged === 0
          ? "Update recorded — no existing contract is affected."
          : `Update recorded — ${res.contracts_flagged} contract${res.contracts_flagged === 1 ? "" : "s"} flagged.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setResult(null);
      }}
      size="lg"
      title="Simulate a regulation update"
      description="Add a new or amended clause and re-check every contract against it."
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Regulation">
          {(p) => <Input {...p} required value={regulation} onChange={(e) => setRegulation(e.target.value)} />}
        </Field>
        <Field label="New or amended clause text">
          {(p) => (
            <Textarea
              {...p}
              required
              rows={5}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. A Data Fiduciary must obtain verifiable parental consent before processing a child's personal data…"
            />
          )}
        </Field>
        <Field label="Effective date">
          {(p) => <Input {...p} type="date" required value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={busy}>
            {busy ? "Re-checking contracts" : "Simulate update and re-check"}
          </Button>
        </div>
      </form>

      {result && (
        <div className="mt-5 border-t border-line pt-4" aria-live="polite">
          <p className="text-sm font-medium text-ink">
            {result.contracts_flagged} contract{result.contracts_flagged === 1 ? "" : "s"} newly flagged
            <span className="font-normal text-muted">
              {" "}
              · {result.findings_created} new finding{result.findings_created === 1 ? "" : "s"}
            </span>
          </p>
          {result.contracts_flagged === 0 ? (
            <p className="mt-1 text-[13px] text-muted">
              No existing contract was affected — or this update was already checked.
            </p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {result.details.map((d) => (
                <li key={d.contract_id} className="flex items-center gap-2 text-[13px]">
                  <Link href={`/contracts/${d.contract_id}`} className="font-medium text-accent hover:underline">
                    {d.filename}
                  </Link>
                  <Badge tone="warn">
                    {d.new_finding_ids.length} new finding{d.new_finding_ids.length === 1 ? "" : "s"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Dialog>
  );
}
