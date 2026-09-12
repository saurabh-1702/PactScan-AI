import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">PactScan AI</h1>
      <p className="max-w-md text-sm text-neutral-500">
        Agentic GraphRAG contract compliance for vendor DPAs — DPDP (primary) +
        GDPR (secondary).
      </p>
      <nav className="mt-2 flex gap-4 text-sm font-medium">
        <Link href="/detect" className="text-sky-700 underline">
          Detect &amp; Suggest
        </Link>
        <Link href="/approvals" className="text-sky-700 underline">
          Approval Queue
        </Link>
      </nav>
    </main>
  );
}
