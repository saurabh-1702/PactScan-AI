# PactScan AI — Final Consolidated Project Document
### Autonomous GraphRAG Platform for Contract Intelligence, Redlining & Perpetual Compliance
*(Master build specification — includes original architecture, scoping decisions, dataset breakdown, regional applicability, and MVP plan)*

---

## 0. How to Use This Document

This is the single source of truth for building PactScan AI in an agentic IDE. It contains:
1. The original product vision and architecture (unchanged)
2. Honest scoping clarifications worked out during planning (region, datasets, sectors)
3. A realistic MVP plan that preserves the full architecture but narrows the data scope
4. Explicit limitations, so the build doesn't silently overclaim capability
5. A fourth, conversational **Ask** agent (Section 4.5) added on top of the original three-agent design, for free-form Q&A/summarization across a client company's entire document portfolio — not just a single attached file
6. **Login page, authentication, and per-tenant encryption** (Section 7.2–7.3)
7. **Tenant dashboard and real-time notifications** (Section 8), including immediate in-app + email alerts the moment Detect or the background Horizon-Scanning agent finds an issue — with document name, page, and exact issue cited
8. **Scaling & performance — Redis caching, cache invalidation, and Celery-based background ingestion** (Section 9), addressing large-portfolio query cost for the Ask agent
9. **Chat-triggered edit requests** (Section 4.5), letting the Ask agent hand off a named-document edit instruction to Suggest for drafting — the mandatory human approval gate (Section 3.5) is explicitly preserved and never bypassed by this shortcut
10. **Document versioning & restore** (Section 4, Agent 3), so an incorrectly approved edit can be reverted — restore is itself an approval-gated, reason-logged, role-restricted action, with repeated restores on one document flagged for admin review rather than freely allowed

Nothing in the originally-scoped architecture has been changed except the explicit additions listed above (Ask agent, login/encryption, dashboard/notifications, scaling/caching). Section numbering reflects these insertions — see the table of section headers for the current layout.

---

## 1. Market Context & Problem Statement

Enterprise legal, procurement, and compliance teams manage thousands of vendor contracts — MSAs, DPAs, NDAs — each subject to overlapping, constantly shifting regulation: the EU AI Act, GDPR, HIPAA, SOC 2, state-level privacy laws, and India's Digital Personal Data Protection (DPDP) Act of 2023.

**Mid-market enterprises (100–2,000 employees)** carry the same regulatory exposure and liability risk as large multinationals, but lack the capital and headcount to run enterprise-grade legal-ops infrastructure. This creates three compounding, systemic failures:

1. **Extraction failure** — Contracts are unstructured PDFs with nested tables, multi-column layouts, digitized signature pages, and complex cross-references. Standard RAG uses naive fixed-token chunking, which severs spatial/referential structure — a liability clause retrieved in isolation loses the definitional context pages earlier that determines its actual meaning.
2. **Reasoning failure** — Legal interpretation requires multi-hop reasoning across a document or document family. Example: an MSA caps liability at $1M on page 3, but a jurisdictional amendment on page 45 or a later SOW silently raises it to $5M for data breaches. Flat vector similarity search cannot execute the multi-hop traversal needed to catch that a later document overrides an earlier one.
3. **Lifecycle failure** — Contracts are reviewed rigorously once, at signing, then never again — even though they remain legally binding indefinitely while the regulatory environment keeps evolving. When a new law passes, there is no automated way to retroactively re-audit an entire legacy contract archive against it.

**Conclusion:** there is no affordable, autonomous, end-to-end system that *ingests → understands → redlines → and perpetually re-audits* a contract portfolio.

---

## 2. The Solution

**PactScan AI** is an agentic, GraphRAG-native legal compliance platform — a virtual AI Legal Associate with a memory that never forgets a contract and never stops watching the regulatory landscape.

It is a **composable, mode-selected system of three independent, user-directed agents**, sitting behind a mode selector, each also independently invocable with a user's own inputs (not a forced one-way assembly line):

| Mode | What happens |
|---|---|
| **Ask** *(added)* | Free-form conversational Q&A across the client company's **entire document portfolio** — every contract ever uploaded, regardless of when — summarization, cross-contract lookup, plain-English explanation, portfolio-wide comparison. Optionally narrowable to a single document. Read-only for questions, no file changes. Can also accept a conversational **edit instruction** naming an existing document, which is handed off to Suggest as a drafted redline — still gated by the same mandatory human approval queue as every other path into Fix & Learn; the chat interface never bypasses approval. Can be used standalone or alongside any other mode. |
| **Detect only** | Parses the document, maps it into the knowledge graph, and evaluates it against playbook/regulation. Produces a severity-scored risk report with citations. Read-only — no drafting, no file changes. |
| **Detect + Suggest** | Findings are handed to a second agent that drafts concrete redline language plus an internal negotiation memo (rationale, precedent, risk exposure) — but never touches the real file. |
| **Detect + Suggest + Fix & Learn** (full pipeline) | The suggested fix passes a human approval gate, is written into the actual document via MCP as a tracked-changes .docx, and the accepted outcome feeds back into the organization's playbook/knowledge graph. |

This directly resolves the three failure modes: layout-aware, graph-based parsing solves extraction failure; multi-hop graph traversal solves reasoning failure; perpetual regulatory horizon-scanning solves lifecycle failure.

---

## 3. The Five Core Innovations

### 3.1 Adversarial Review Pair (Contrarian + Judge Agents)
When the extraction agent flags a risky clause, a **Contrarian Agent** is instantiated to construct the strongest possible argument that the clause is actually compliant or advantageous (adopting the counterparty's perspective). A **Judge Agent** then reconciles both positions into a final, confidence-scored recommendation. This mirrors human appellate/adversarial review and reduces hallucinated risk findings.

### 3.2 Negotiation Twin
Before any redline reaches a human, a **Negotiation Twin** agent role-plays the counterparty's legal team, predicting their most likely objection and autonomously drafting fallback language in advance — e.g., *"If they reject the strict mutual liability cap, your pre-approved fallback is [Clause X]."*

### 3.3 Bitemporal Knowledge Graph
Built on **Neo4j**, every clause/obligation/regulatory node carries a dual-axis temporal stamp:
- **`validFrom` / `validTo`** — the window during which an interpretation or statute was legally binding
- **`knownFrom`** — the moment the organization became aware of that interpretation

This enables queries like *"What was our data-breach liability exposure across all EU vendor DPAs on Jan 1, 2024, before the Q2 amendments?"*

### 3.4 Regulatory Horizon-Scanning Agent
A scheduled, asynchronous agent continuously ingests regulatory feeds, embeds them as sub-graphs, and runs an automated diff against the live, multi-tenant contract graph — retroactively flagging every existing contract that now needs remediation, without human intervention.

### 3.5 Governance / Agent Control Plane (Verifiable Generation)
No agent has write access to a production document or external communication without passing a mandatory **Human-in-the-Loop (HITL) gate**. The system generates two distinct outputs: a clean, external tracked-changes document for the counterparty, and an internal negotiation memo for internal use only. **This rule applies uniformly regardless of how a redline was requested** — whether triggered by a Detect finding, a manually flagged clause, or a conversational edit instruction typed into the Ask agent (Section 4.5) — every path into Suggest produces a draft only, and every draft still requires the same logged human approval event before Fix & Learn's Executor can write anything via MCP.

---

## 4. Agent Features (Detailed)

### Agent 1 — Detect (standalone-capable)
*Input: raw contract file → Output: structured risk report*
- Layout-aware ingestion (nested tables, multi-column text, OCR/vision fallback) via LlamaParse
- Structured clause extraction validated against PydanticAI schemas, benchmarked on CUAD — low-confidence fields flagged, never guessed
- NLI to determine whether a clause **entails, contradicts, or is neutral** to the required compliance posture
- Writes entities/relationships into the temporal Neo4j knowledge graph
- Live cross-check against the regulatory horizon-scanning feed
- Output: severity-scored risk report citing exact page numbers, section headers, statutes in conflict

### Agent 2 — Suggest (standalone-capable or chained from Detect)
*Input: risk report (or user-supplied flagged clauses) → Output: redline language + negotiation memo, no file writes*
- **Retriever agent** — hybrid vector + Cypher graph traversal (Neo4j GraphRAG)
- **Contrarian agent** — argues the counterparty's best-case interpretation
- **Judge agent** — reconciles into a confidence-scored recommended position
- **Negotiation Twin** — predicts counterparty pushback, drafts fallback language
- Dual-output: raw replacement text *and* full internal negotiation memo

### Agent 3 — Fix & Learn (standalone-capable or chained from Suggest)
*Input: approved redline → Output: edit applied to the real document + updated playbook/eval baseline*
- **Human approval gate** — diff-view queue; no unsupervised write access
- **Executor agent** — uses MCP to write approved changes into the real Word/Google Doc as tracked changes; drafts/files amendments
- **Visual diff / QA agent** — renders before/after page images to catch formatting breakage
- **Learning loop** — approved/rejected outcomes feed back into playbook and eval harness

**Document versioning & restore (added):** every time the Executor writes an approved edit, the pre-edit version of the document is archived rather than overwritten — the correct mental model is **version history with restore**, not a generic "undo," since a literal undo could too easily become a silent, unaccountable action on a legal document.

- **Storage:** each version is preserved in the existing S3-compatible object storage (Section 6), tracked in a new `document_versions` table linking `document_id`, `version_number`, storage path, timestamp, and the `approval_id` that produced it — no new storage technology introduced.
- **Restore is a first-class, approval-gated action, not a shortcut around governance.** If a client later determines an approved fix was wrong, they can request a restore to a prior version — but this request goes through the **exact same human approval gate** as any other edit (Section 3.5). It is logged in `audit_log` identically to a forward edit, and only Fix & Learn's Executor (via MCP) can actually perform it, once approved. A restore is never instant or silent.
- **Abuse-prevention controls, specifically to prevent flip-flopping a document back and forth on demand:**
  - **Reason required:** a restore request must include a stated justification (e.g., "the approved liability cap change was based on a misread clause"), stored permanently — this mirrors the rationale already required for `redline_suggestions` and `approvals`, so no new pattern is introduced.
  - **Role-gated approval:** only a reviewer/compliance-officer or admin role (Section 7.2's existing role field) can approve a restore — an end-user can request one, but cannot self-approve it, the same asymmetry already built into the original approval-gate design.
  - **Anomaly flagging, not hard-blocking:** if a single document accumulates more than a defined threshold of restore events within a time window (e.g., 2+ restores in 30 days), it is flagged for admin review rather than being blocked outright — this makes repeated back-and-forth visible and questionable rather than either silently permitted or rigidly forbidden, which matters because outright blocking could itself prevent a legitimate second correction.
  - **Nothing is ever deleted.** Restoring to an earlier version does not erase the versions in between — it simply makes the restored version current again and logs a new event. The complete version history, including any flip-flopping, remains permanently visible to an auditor, which is itself the primary deterrent against misuse.
  - **Restore can only target a version that was itself previously approved** — it cannot be used to introduce new, unapproved content disguised as a "restore," keeping it inside the same governance model as every other write.

### 4.5 Agent 0 — Ask (standalone, conversational — added feature)
*Input: free-form user question (optionally scoped to one document) → Output: grounded, cited natural-language answer drawn from the company's entire document portfolio, no file writes*

This is a conversational layer added on top of the original three-agent design, so a client can ask questions the way they would to an LLM chatbot — but grounded across **every contract their company has ever uploaded**, not just a single attached file. This matches how a company would actually use it: a compliance officer doesn't always know which of 200 vendor contracts has the answer — they just want to ask the question.

**Retrieval scope — company-wide by default:**
- Because the Neo4j graph is already **partitioned per-tenant** (Section 7), every contract a company has ever uploaded lives in the same tenant-scoped graph, connected by relationships, regardless of *when* it was added.
- The Ask agent's Retriever therefore searches **across the entire tenant's document portfolio by default** — e.g. *"Which of our vendor contracts have a liability cap under $2M?"* or *"Have we ever agreed to arbitration in the EU with any vendor?"* — pulling matching clauses from however many contracts are relevant, not just one.
- A client can still **narrow the scope to a single document** if they want (e.g. "just answer from the Acme MSA") — this is an optional filter on top of the same Retriever, not a separate system.
- Time of upload is irrelevant to retrieval — a contract uploaded two years ago is just as queryable as one uploaded five minutes ago, since both are already graph nodes in the same tenant partition.

**Why it doesn't need new core infrastructure:**
It reuses components already built for the other three agents rather than introducing a parallel system:
- The same **LlamaParse ingestion** and **Neo4j knowledge graph** every document was already mapped into for Detect
- The same **hybrid vector + Cypher GraphRAG Retriever** built for the Suggest Agent — extended to query across all document nodes under a tenant rather than a single document's nodes
- The same **PydanticAI-style grounding rule** used everywhere else in the system: every answer must cite a specific graph node/clause/**document name**/page — if nothing in the graph supports an answer, the agent must explicitly say so rather than fabricate (Section 12.8's abstention rule applies here too)

**Critical requirement — per-answer document attribution:**
Because answers can now be synthesized from multiple contracts at once, every claim in an Ask response must state **which specific document** it came from (e.g. *"According to the Acme MSA (signed Mar 2024), the liability cap is $1M; according to the Beta DPA (signed Jan 2025), it's $3M"*) — otherwise a company gets a correct-sounding answer with no way to know which real contract it applies to. This is enforced the same way Detect's findings already cite exact page/section (Section 4, Agent 1).

**What's added specifically for this feature:**
- **Conversation/session state** — multi-turn memory so follow-up questions ("what about for the EU subsidiary?") resolve correctly, using **LangGraph's existing checkpointing** (already in the stack for durable agent state) rather than a new memory system
- **Scope-classifier sub-step** — a lightweight router check (also LangGraph, reusing the existing mode-selector pattern) that (a) keeps the conversation contract-focused, declining off-topic/general-legal-advice questions, and (b) detects whether the user wants portfolio-wide or single-document scope
- **Cross-document retrieval ranking** — since a query may now match clauses across many contracts, the Retriever needs to rank and select the most relevant documents/clauses rather than returning everything; this reuses Neo4j GraphRAG's existing hybrid vector + Cypher scoring, just applied over a larger node set
- **Streaming responses** — for a natural chat feel, answers stream token-by-token over the existing FastAPI backend using Server-Sent Events (SSE), which FastAPI supports natively — no new backend framework required
- **Faithfulness scoring on chat answers** — the same **RAGAS**-based automated judge already used in the Self-Grounding Evaluation Loop (Section 11) is extended to score every chat answer's faithfulness/context relevance, not just Detect/Suggest outputs
- **Cheaper/faster model routing for latency** — routine single-document Q&A (summarization, simple lookups) is routed to a lower tier of the 7-tier fallback chain (Section 6's implementation note); complex cross-document or comparative questions preferentially try the highest-quality available tier first, using the same cost/quality routing logic already in place for Detect vs. Suggest

**Performance note (portfolio-wide scope, at scale):**
Searching across one document is fast; searching across hundreds is a different retrieval problem. As a company's contract volume grows, Neo4j's indexing (vector index + graph indexes on tenant/document boundaries) needs to stay tenant-scoped so a query never accidentally searches across tenants (a hard security requirement, not just a performance one — see Section 7's cryptographic per-tenant partitioning), and retrieval should be capped/paginated (e.g., top-N most relevant documents) rather than exhaustively scanning an entire large portfolio on every query.

**Chat-triggered edit requests — a new entry point into Suggest, not a new write path (added):**
A client can name a specific document already in the portfolio and ask for an edit conversationally — e.g., *"Edit the Acme MSA — change the liability cap to $2M"* — without re-attaching the file, since it's already ingested and identifiable in the tenant's graph (same lookup-by-name mechanism used for any Ask query).

- **What this actually does under the hood:** the scope-classifier (already part of Ask, described above) detects that the message is an *edit instruction* rather than a question, and hands it off as a new, chat-triggered entry point into the **Suggest agent** (Section 4, Agent 2) — the exact same Retriever → Contrarian → Judge → Negotiation Twin pipeline that already drafts redlines from a Detect finding or a manually flagged clause. The only thing that's new is the trigger; the drafting logic is entirely reused, not duplicated.
- **What this does NOT do — the mandatory approval gate is unchanged:** the output of this chat-triggered request is a **drafted redline + negotiation memo shown in-app, exactly like any other Suggest output** — it does **not** write to the real document. It still must pass through the same human approval queue (Section 3.5, Section 4 Agent 3, Section 12.6) before the Fix & Learn agent's Executor is ever invoked via MCP. A casual chat message can request a *draft*; it can never, by itself, cause a real edit to a real document. This preserves the core governance principle (Section 3.5) that no agent has write access without a logged human approval event — a chat interface does not create an exception to that rule.
- **Why this distinction matters enough to state explicitly:** every other addition in this document (Ask, dashboard, notifications, caching) was deliberately scoped to never touch the write path. This is the one addition that sits right next to the write path, which is exactly why the approval gate is called out here as non-negotiable rather than left implicit.

**Example interactions:**
- *"Summarize this contract in plain English"* (single-document scope)
- *"Which of our contracts have a liability cap under $2M?"* (portfolio-wide)
- *"Have we agreed to arbitration with any EU vendor?"* (portfolio-wide)
- *"Compare this NDA to the one we signed with Vendor X last year"* (cross-document, explicit comparison)
- *"Do any of our vendor contracts currently violate DPDP's parental consent requirement?"* (portfolio-wide, regulation-aware — reuses the same regulatory nodes Detect already cross-checks against)
- *"Edit the Acme MSA — change the liability cap to $2M"* (chat-triggered Suggest entry point — produces a draft redline + memo in the approval queue, never a direct file edit)

**Guardrail — why this is safer than a generic chatbot:** a plain LLM chatbot pasted a contract can hallucinate an answer with total confidence, has no way to answer portfolio-wide questions at all, and — critically — has no concept of a human approval gate, so a careless prompt could in principle cause it to "just edit the file." Because Ask is graph-grounded, reuses the same abstention rule as the rest of the system, cites the exact source document for every claim, and routes every edit request through the same mandatory approval queue as the rest of the system, every answer traces back to a real clause in a real, named contract, and every edit request stays a draft until a human signs off — or the system says it doesn't know. This is a genuine differentiator to highlight in a demo: a client can ask company-wide questions, and even request edits conversationally, with the same governance guarantees as the structured pipeline.



- Scheduled Regulatory Horizon-Scanning process continuously ingests feeds, embeds them, diffs against the live contract graph
- When a new rule affects existing contracts, auto-generates a Detect-style finding per affected contract → can hand off into Suggest and, after approval, Fix & Learn

---

## 5. Where Agentic AI, RAG, and MCP Live

| Pillar | Role |
|---|---|
| **Agentic AI** | Every module is a multi-step, autonomous, tool-using agent. Detect decides when to fall back to vision OCR. Suggest is a coordinated sub-agent team. Fix & Learn autonomously drafts redlines/addendums and updates the playbook. Ask is a conversational agent that reuses the same retrieval/grounding infrastructure for free-form Q&A. |
| **RAG (graph-native)** | Neo4j knowledge graph is the retrieval corpus, connected by explicit relationships (e.g. `[SOW_CLAUSE] -[:OVERRIDES]-> [MSA_CLAUSE]`). Hybrid vector + Cypher traversal enables multi-hop reasoning. Horizon-scanning is itself a continuous RAG pipeline; Ask is a conversational front-end onto the same RAG layer. |
| **MCP** | Standardized layer for agents acting on external systems: Fix & Learn writes into Word/Google Docs and files amendments via DocuSign; ingestion pulls from inboxes/cloud storage/ERPs. |

---

## 6. Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Document parsing | LlamaParse (+ Unstructured/OCR fallback) | Best-in-class spatial/table-preserving PDF parsing |
| Structured validation | PydanticAI | Type-safe schema enforcement, prevents hallucinated fields |
| Knowledge graph | Neo4j + Neo4j GraphRAG | Native hybrid vector + Cypher traversal; bitemporal modeling |
| Orchestration | LangGraph 1.0 | Each agent its own subgraph; router invokes only what's needed; durable checkpointing |
| High-stakes execution agent | Claude Agent SDK *(original design)* — see implementation note below | Safety constraints for write-access to real legal documents; native tool use |
| LLM(s) | Claude Opus-class model for reasoning/judgment; smaller/cheaper model for high-volume extraction *(original design)* — see implementation note below | Balances reasoning quality vs. cost |
| Document write-access | MCP servers (Google Docs / Microsoft Word / DocuSign Agreement Cloud) | Standardized, auditable tool-call interface |
| Regulatory feed ingestion | Web search/RSS + scheduled jobs (LangGraph cron or Temporal.io) | Continuous horizon-scanning |
| Governance / control plane | Custom approval-queue service | No agent writes to production without a logged human approval event |
| Evaluation dataset | CUAD v1 | Ground truth for extraction accuracy and regression testing |
| Observability | LangSmith | Full trace of every agent decision |
| Agent sandboxing | E2B / Modal-style sandboxes | Durable, isolated execution for code-executing sub-agents |
| Backend | FastAPI (Python) | Matches PydanticAI/LangGraph ecosystem |
| Frontend | Next.js/React with live redline diff viewer | Reviewer UX for the approval gate |
| Auth/multi-tenancy | Auth0/Clerk (login page, SSO, MFA) + per-tenant Neo4j graph partitioning | SaaS-ready isolation; JWT carries `tenant_id`/`role` for every request |
| Per-tenant encryption *(added)* | AWS KMS / Google Cloud KMS / HashiCorp Vault (matches Terraform-provisioned cloud) + TLS 1.3 in transit | Independent, rotatable encryption key per tenant — contains blast radius of any single-tenant breach; complements, doesn't replace, tenant-scoped access control |
| Application database | PostgreSQL | Operational state — tenants, users, contracts, runs, findings, approvals, audit log |
| Object storage | S3-compatible | Raw contracts + before/after page images for visual diff QA |
| Deployment | Docker/Kubernetes (or ECS/Fargate) | Standard production deployment |
| Infrastructure as Code | Terraform | Provisions Postgres, Neo4j Aura, object storage, K8s cluster |
| Monitoring | Prometheus + Grafana, Sentry, Loki/ELK | Infra metrics, error tracking, feeds the audit trail |
| Deliverable generation | Python-docx, lxml/OOXML processing | Converts internal JSON into tracked-changes .docx / redline PDFs |
| Dashboard visualization *(added)* | Recharts (Next.js frontend, already available) | Renders portfolio health, findings pipeline, and regulatory exposure panels straight from existing Postgres tables — no new charting stack introduced |
| Notification delivery *(added)* | In-app (read from existing `findings` table) + transactional email (Resend / SendGrid / AWS SES) | Fires as a side-effect on `findings` writes from both Detect and Horizon-Scanning agents; severity-aware routing avoids alert fatigue |
| Query-result caching *(added)* | Redis | Caches Ask agent answers keyed by `(tenant_id, question, scope)`; reverse-indexed by source `document_id`s for targeted invalidation |
| Background ingestion queue *(added)* | Celery (+ Redis or RabbitMQ as broker) | Handles heavy bulk document parsing/embedding/graph-writing asynchronously (e.g., onboarding 500 documents at once); deliberately not used on the live Ask-query path |
| Conversational session state *(Ask agent)* | LangGraph checkpointing (existing) + PostgreSQL `chat_sessions`/`chat_messages` tables | Multi-turn memory reusing the orchestration layer already in the stack — no new memory framework introduced |
| Streaming chat responses *(Ask agent)* | FastAPI native Server-Sent Events (SSE) | Token-by-token streaming over the existing backend; no new server framework needed |
| Chat answer grounding/scoring *(Ask agent)* | RAGAS (existing, extended from Section 11's eval loop) | Reuses the same faithfulness/abstention scoring already built for Detect/Suggest outputs, applied to conversational answers too |

**PostgreSQL application schema:** `tenants`/`users`/`roles`, `contracts`, `agent_runs`, `findings`, `redline_suggestions`, `approvals`, `audit_log`, `playbook_versions`, `chat_sessions`/`chat_messages` *(added for Ask agent)*, `notifications` *(added — tracks in-app/email delivery status per finding)*, `document_versions` *(added — tracks every Fix & Learn edit as a preserved, restorable version, linked to its originating `approval_id`; isolated table, no schema conflict with existing entities)*.

### Implementation Note — LLM Provider Substitution (Claude → Gemini, free-tier build)

The original architecture (above) specifies Claude (Anthropic) as the reasoning model, including the Claude Agent SDK for the high-stakes Executor. **For the actual student-project build, this is substituted with Google Gemini**, for a concrete, disclosed reason: the Anthropic account backing this project could not be funded with API credits, while a Google AI Studio account with free-tier access was available.

This substitution is implemented, not improvised around case-by-case:
- **A provider-agnostic LLM abstraction** (`backend\app\llm\client.py`) sits behind every agent call (Detect's NLI classification, Suggest's drafting, the adversarial review pair if built, Ask's retrieval/answering) — no agent calls a model SDK directly, so the provider itself is a one-file swap, not a scattered rewrite.
- **A three-layer fallback architecture** is used in place of the single Claude Opus-class model originally specified, since no single free Gemini tier or account has sufficient daily quota alone: (1) a **local response cache**, keyed by prompt content plus a prompt-version identifier so a logic change never serves a stale cached answer; (2) a **7-tier model chain** — `gemini-3.8-flash` → `gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemma-4-31b`, ordered quality-first then volume-fallback, each tier a genuinely independent quota pool; (3) a **multi-account fallback loop** across 3 separate Google AI Studio accounts (extensible to more via a simple comma-separated config list, no code change required), walking the full 7-tier chain under one account before advancing to the next. A dedicated `gemini-embedding-001` pool handles Phase 2's vector embeddings separately.
- **`gemini-3.1-pro-preview`** (Gemini's closest equivalent to the originally-specified Opus-class reasoning model) is configured but inactive, since it requires a billing account not currently attached to the project — kept as a one-line upgrade path, exactly the same pattern as the DPDP/GDPR-only MVP regulatory scope in Section 17.
- The **Claude Agent SDK's specific safety-constraint framing** for the Executor is reproduced functionally, not via that SDK — the mandatory human-approval gate (Section 3.5), the guard-clause check inside the Executor itself, and the append-only audit log together provide the same governance guarantee, implemented directly in the FastAPI backend rather than via Anthropic's agent framework.

**Why this is disclosed here rather than silently edited into the original table:** the "Claude Opus-class" and "Claude Agent SDK" rows above represent the intended production-grade design and are worth keeping visible as the aspirational architecture — a real, funded deployment would likely use them, or a comparable frontier-model provider with committed API spend. The Gemini substitution is a build-time constraint, not a retraction of that design intent, and should be presented as such if asked: *"the architecture is model-agnostic by design; this build runs on Gemini's free tier for cost reasons, with Claude (or another frontier provider) as the documented upgrade path once funded."*

---

## 7. Multi-Tenant Architecture, Authentication & Per-Tenant Encryption

### 7.1 Multi-tenancy (original)
- Cryptographically partitioned per-tenant graphs in Neo4j; Neo4j Graph Data Science (GDS) library (Filtered Node Similarity, K-Nearest Neighbors) clusters similar contracts and flags anomalous clauses within a client's isolated portfolio.
- **Hybrid SaaS pricing:** baseline platform fee (for maintaining the temporal graph + horizon-scanning agents) + usage-based micro-transaction fee per clause resolved by the Fix Agent.

### 7.2 Login Page & Authentication (added)
A proper login page is the entry point every user (client, reviewer, admin) passes through before reaching any agent — this reuses the **Auth0/Clerk** entry already named in the tech stack (Section 6) rather than introducing a new auth provider.

- **Frontend:** a Next.js login page (email/password, plus SSO/OAuth options — Google, Microsoft — since enterprise legal buyers commonly require SSO for procurement approval) built using Auth0's or Clerk's hosted login components, so password handling, MFA, and session tokens are never handled manually by the app's own backend.
- **Session/token layer:** on successful login, the identity provider issues a signed JWT containing the user's `tenant_id` and `role` (e.g., end-user, reviewer/compliance officer, admin) — the same `tenants`/`users`/`roles` Postgres tables already defined in Section 6 back this, no new schema needed.
- **Every downstream request is tenant-scoped from the token, not from user input** — the `tenant_id` in the JWT determines which Neo4j graph partition and which Postgres rows a request can touch, so a user can never accidentally (or maliciously) query another company's data by changing a request parameter.
- **MFA** — enabled via the identity provider's built-in support (Auth0/Clerk both support this natively), important given the sensitivity of contract data.

### 7.3 Per-Tenant Encryption (added)
This is a distinct concern from login/authentication — authentication controls *who* can ask for data; encryption controls what happens to the *data itself*, both at rest and in transit. Two layers, kept separate so one weak layer doesn't compromise the other:

**Encryption in transit:**
- Standard **TLS 1.3** for every connection — frontend↔backend, backend↔Neo4j, backend↔Postgres, backend↔MCP write targets (Word/Google Docs/DocuSign). This is table stakes, not novel, but worth stating explicitly since contract data is highly sensitive.

**Encryption at rest — per-tenant keys (the more important design decision):**
- Rather than one shared encryption key for the whole database, each tenant gets its **own encryption key**, managed via a **KMS (Key Management Service)** — e.g., AWS KMS, Google Cloud KMS, or HashiCorp Vault, matching whichever cloud the Terraform/Kubernetes deployment (Section 6) targets.
- **Why this matters specifically for this project:** if one tenant's data were ever compromised (e.g., a compromised admin credential, a misconfigured query), per-tenant keys mean the blast radius is contained to that one company's contracts — every other tenant's data remains encrypted under a completely separate key, unreadable even with database-level access.
- **What gets encrypted with the tenant key:** raw contract files in S3-compatible object storage (Section 6), sensitive fields in Postgres (e.g., `findings`, `redline_suggestions`, `chat_messages` content), and — where the database technology supports it — property-level encryption on sensitive Neo4j node fields (contract text, clause content).
- **Key rotation:** tenant keys are rotatable independently through the KMS without needing to re-encrypt every other tenant's data, and a tenant offboarding (contract cancelled) can have its key destroyed, cryptographically shredding that tenant's data even if raw ciphertext is never physically deleted.

### 7.4 Why this doesn't clash with anything already in the stack
- **No new auth provider** — reuses Auth0/Clerk already named in Section 6's tech stack table.
- **No new database or schema** — reuses the existing `tenants`/`users`/`roles` Postgres tables and the existing per-tenant Neo4j graph partitioning from Section 7.1; encryption is a property applied *to* that existing partitioning, not a redesign of it.
- **No conflict with the Ask agent's portfolio-wide retrieval (Section 4.5)** — because retrieval is already scoped by `tenant_id` from the JWT, per-tenant encryption sits underneath that boundary and reinforces it; a cross-tenant retrieval bug would still be blocked by the encryption layer even if the application-layer scoping ever failed, giving defense-in-depth rather than relying on one control alone.
- **No conflict with MCP write access (Fix & Learn, Section 4)** — the Executor agent's MCP calls are already gated by the human approval flow and tenant-scoped credentials; encryption at rest doesn't change that flow, it just protects the underlying stored data the flow operates on.

---

## 8. Tenant Dashboard & Real-Time Notifications (added)

### 8.1 Tenant Dashboard
A visual layer on top of data the system already generates — no new backend logic required, since every number displayed is already sitting in the existing Postgres tables (`findings`, `redline_suggestions`, `approvals`, `audit_log`) defined in Section 6. This is the "home screen" a tenant sees on login, right after the login page/auth flow in Section 7.2.

**Design decision (default assumption — adjustable):** dashboards are **role-based**, reusing the `role` field already carried in the JWT (Section 7.2) and the existing `tenants`/`users`/`roles` schema. An end-user/client, a reviewer/compliance officer, and an admin each see a view tailored to their job, not one generic screen. This was chosen over a single unified dashboard because it better matches how enterprise legal-tech buyers actually evaluate a tool (Section 16's competitor list — Ironclad, LegalOn, etc. — all differentiate by role), and it requires no new schema, just conditional rendering on data already scoped by tenant.

**What it displays, by section:**

| Panel | Data source | What it shows |
|---|---|---|
| Portfolio health overview | `contracts` + `findings` | Total contracts, broken down ✅ Compliant / ⚠️ Needs review / 🔴 High-risk; a compliance-score trend line over time |
| Findings pipeline (kanban-style) | `findings` → `redline_suggestions` → `approvals` | Status-grouped view: 🆕 New finding → ✍️ Redline suggested → ⏳ Pending approval → ✅ Fixed & applied → ❌ Rejected |
| Regulatory exposure panel | `findings` filtered by regulation tag, written by the Horizon-Scanning Agent (Section 4, Background Feature) | Live counter of contracts newly flagged when a regulation changes; breakdown by regulation (GDPR / DPDP / HIPAA / etc.) |
| Per-contract drill-down | `contracts` + `findings` + graph node lookup | Full finding history for one contract, current redline status, and a mini Ask-agent chat (Section 4.5) pre-scoped to just that document |
| Reviewer approval queue | `approvals` (already defined in Section 12.6's workflow) | Sorted by severity/confidence — the dashboard is simply the UI surface for the approval workflow that already existed in the design |

**Tech notes:** built on the existing Next.js frontend (Section 6) with a charting library such as Recharts; every query is automatically tenant-scoped via the same `tenant_id`-bearing JWT used everywhere else (Section 7.2) — the dashboard cannot be pointed at another tenant's data by construction, not just by convention.

### 8.2 Real-Time Notifications
The moment the Detect Agent (or the background Horizon-Scanning Agent) writes a new row into `findings`, a notification fires — implemented as a side-effect hook on that write, not a separate polling system or new agent.

**Trigger scope — confirmed:** notifications fire for **both**:
- Findings generated when a tenant actively uploads a new document (Detect Agent, Section 4, Agent 1)
- Findings generated in the background when the **Horizon-Scanning Agent** flags an *already-signed, older* contract because a regulation changed (Section 4, Background Feature; Section 12.5) — this means a compliance officer gets notified even on a day they didn't upload anything, which is the direct product expression of the "lifecycle failure" fix from Section 1 and the perpetual-compliance pitch in Section 3.4.

**What the notification contains** — reuses the exact citation format Detect/Horizon-Scanning already produce (Section 4), reformatted as a short alert rather than a full report:

> ⚠️ **New finding — High severity**
> Document: *Acme_MSA_DataVendor_2024.pdf*
> Location: Page 45, Clause 4.1 (SOW Addendum)
> Issue: Liability cap effectively raised to $5M for data-breach events, overriding Section 8.2(a)
> Confidence: 91%
> [Open finding →]

**Channels — confirmed: in-app + email**

| Channel | Mechanism | Role |
|---|---|---|
| In-app | Notification bell + dashboard badge, reading from the same `findings` table the dashboard (8.1) already queries | Primary channel for live demo; zero new infrastructure |
| Email | Transactional email service — e.g., Resend, SendGrid, or AWS SES (matches whichever cloud Terraform already provisions, Section 6) | "Production-real" channel; also the natural channel for a compliance officer who wasn't logged in when Horizon-Scanning fired |

**Severity-aware routing (to avoid alert fatigue):** only 🔴 High-severity findings trigger an immediate push/email; 🟡 Medium and 🟢 Low severity findings appear on the dashboard (8.1) without an interrupting alert. This reuses the severity score Detect already computes (Section 4) — no new scoring logic needed.

### 8.3 Why this doesn't clash with anything already in the stack
- **No new agent, no new write path** — both features only *read* from tables (`findings`, `redline_suggestions`, `approvals`) that Detect, Suggest, and Fix & Learn already populate; they cannot interfere with those agents' logic.
- **No new auth model** — the dashboard's tenant/role scoping reuses the exact JWT and `tenants`/`users`/`roles` schema from Section 7.2; no parallel permission system introduced.
- **Notification hook is a side-effect, not a blocking step** — firing a notification after a `findings` write does not slow down or gate the Detect/Horizon-Scanning agents themselves; if the notification service is briefly unavailable, the finding is still safely written and simply appears on the dashboard on next login.
- **Consistent with the encryption boundary (Section 7.3)** — email notification content should stay to summary-level detail (document name, page, short issue description) rather than reproducing full clause text, keeping sensitive contract language inside the encrypted, tenant-scoped system rather than in a third-party email provider's logs.

---

## 9. Scaling & Performance — Caching, Cache Invalidation, and Background Ingestion (added)

This section addresses a real systems concern: once a tenant has a large document portfolio (e.g., 500+ contracts), the **Ask agent's portfolio-wide retrieval** (Section 4.5) and repeated similar questions from multiple users need a deliberate performance design — not just "it'll scale because the graph is fast."

### 9.1 What actually scales well vs. what doesn't

It's important to be precise about where the real cost lives, since the intuitive worry ("500 documents means searching through 500 documents") is not quite how the system works:

- **Retrieval itself is sub-linear, not a linear scan.** The Neo4j vector index (already in the stack, Section 6) is built for approximate nearest-neighbor search — it does not compare a query against every node in the graph one by one. Querying across 500 documents is not dramatically slower than querying across 50, because GraphRAG (chosen specifically for this reason in Section 1) skips irrelevant regions of the graph rather than scanning them.
- **The real cost drivers are:** (a) how many chunks/nodes get pulled into the LLM's context per answer, (b) how often the *same or similar* question gets repeated across users, and (c) the cost of ingesting/embedding a large batch of new documents in the first place.
- This reframing matters because it means the fix is **not** "make search faster" (it's already reasonably fast by design) — it's **caching repeated results** and **moving heavy one-time ingestion work off the request path.**

### 9.2 Redis — Query-Result Caching (not a search-avoidance layer)

Redis is added as a cache for **Ask agent answers**, sitting in front of the GraphRAG Retriever:

- **Cache key:** a hash of `(tenant_id, normalized question text, scope — portfolio-wide or single-document)`.
- **Cache value:** the full answer *plus* the list of source `document_id`s (and ideally clause/node IDs) that the answer was actually grounded in — this list already exists, since every Ask answer must cite its sources (Section 4.5's attribution requirement); it is simply also stored alongside the cached answer rather than only shown to the user.
- **Effect:** if five different employees at a company ask a similar question ("what's our standard liability cap across vendor contracts?") within a short window, only the first triggers a real GraphRAG retrieval + LLM call. The rest are served instantly from Redis — meaningfully cutting both latency and LLM cost on frequently-asked questions, which is realistic in a compliance team's day-to-day usage.
- **Where it sits architecturally:** a cache-check step at the front of the Ask agent's LangGraph subgraph (Section 4.5) — if a valid cache hit exists, skip the Retriever and LLM call entirely; if not, run retrieval as normal and populate the cache afterward. No change to Detect, Suggest, or Fix & Learn — this is scoped entirely to Ask's read path.

### 9.3 Cache Invalidation — the part that has to be designed deliberately

Caching a `question → answer` pair with no link back to its source documents would create exactly the stale-answer risk flagged earlier: if Fix & Learn edits a contract, or Horizon-Scanning adds a new finding to one, any previously cached answer touching that document could now be wrong — which is a real liability risk for a compliance tool, not just a UX inconvenience. This is solved with two complementary mechanisms, not one:

**(a) Reverse-index invalidation (primary mechanism)**
- Maintain a Redis-backed (or lightweight Postgres) reverse index: `document_id → [list of cache_keys whose answer drew from this document]`.
- This reuses data the system already has — every cached answer already stores which documents it cited (Section 9.2) — so building the reverse index is just writing that same relationship in the opposite direction at cache-write time.
- **Invalidation trigger — a side-effect hook, same pattern as the notification system (Section 8.2):**
  - Fix & Learn writes an approved edit into a document → look up that `document_id` in the reverse index → delete every cache entry that used it.
  - Horizon-Scanning adds a new finding to a contract → same trigger, same lookup, same deletion.
- This is intentionally **coarse-grained but safe**: it invalidates *any* cached answer that touched a changed document, even if the specific edit didn't affect the part the cached answer was actually about. That tradeoff is correct for a legal-compliance product — an unnecessary cache miss costs a little latency; a stale legal answer costs trust and potentially real liability.

**(b) TTL (time-to-live) as a safety net (secondary mechanism)**
- Every cached answer also carries a modest TTL (e.g., 15–30 minutes) regardless of the reverse-index logic above.
- This exists specifically to self-heal any edge case the invalidation hook might miss — a bounded staleness window rather than an indefinite one, so a single missed invalidation trigger cannot cause a permanently wrong cached answer.

**(c) Portfolio-wide questions invalidate more often — by design, not as a flaw**
A query like *"which of our contracts have a liability cap under $2M?"* draws from many documents at once, so its cache entry is linked to all of them in the reverse index — meaning it gets invalidated whenever *any* of those documents changes. This is the intended, correct behavior: broad questions should be treated as more perishable than narrow, single-document questions, precisely because they depend on more moving parts.

### 9.4 Celery — Background Ingestion, Not Live Query Handling

Celery (a background task queue) is scoped specifically to **document ingestion**, not to answering live Ask-agent questions:

- **Good fit:** when a tenant bulk-uploads a large batch of contracts (e.g., onboarding with 500 existing documents at once), parsing (LlamaParse), embedding, and Neo4j graph-writing all of them is genuinely heavy, slow, and appropriate for async background processing — exactly Celery's intended use case. The user gets an "ingesting N documents, you'll be notified when ready" state (reusing the same notification mechanism from Section 8.2) rather than a blocked UI.
- **Deliberately not used for:** the live Ask-agent conversation itself. A person typing a question expects a fast, streaming response (already designed via SSE, Section 4.5/8.2) — routing a live chat query through a background task queue would add latency and complexity that works against the "chat like an LLM" experience the Ask agent is meant to provide. Celery therefore sits only on the ingestion path, never on the query-answering path.

### 9.5 Why this doesn't clash with anything already in the stack
- **No change to Detect, Suggest, or Fix & Learn's logic** — caching and its invalidation hooks are entirely scoped to the Ask agent's read path and to write-events those other agents already produce; none of their internal reasoning changes.
- **Reuses the existing notification-hook pattern (Section 8.2)** rather than introducing a new event system — the same "side-effect on `findings`/document write" mechanism now also triggers cache invalidation, not just a notification.
- **Reuses existing source-attribution data (Section 4.5)** rather than computing anything new — the document list needed for the reverse index is the same list already required for citation accuracy.
- **No conflict with per-tenant encryption (Section 7.3)** — cache keys and values are scoped by `tenant_id` exactly like every other data path in the system, and cached answer text should stay to the same summary-appropriate detail level already recommended for notifications (Section 8.3), rather than caching full raw clause text unnecessarily in Redis.
- **No conflict with multi-tenancy** — the reverse index and cache keys are always tenant-scoped, so a cache invalidation event in one tenant's portfolio can never touch another tenant's cached answers.

---

## 10. Deliverable Generation (OOXML Bridging)

The Fix Agent outputs a structured JSON object (original text, proposed redline, risk tier, rationale). lxml processing maps this into Office Open XML, producing a true `.docx` with native Tracked Changes. Normalization fixes common AI-output formatting issues (curly quotes, whitespace artifacts, split runs). The control plane strictly separates the **external** clean document from the **internal** negotiation memo.

---

## 11. Self-Grounding Evaluation Loop

- On every LLM weight, retrieval-logic, or prompt update, a regression suite runs automatically against held-out CUAD and ContractNLI subsets.
- Generative redline quality scored with **BERTScore**, **ROUGE-L**, **Edit Similarity**, and **LLM-as-a-Judge**.
- Full execution traces permanently logged and cryptographically signed for enterprise auditors.
- An automated judge (RAGAS or custom LLM-as-judge) scores faithfulness/context relevance on every live output; low-confidence/high-severity outputs go to human spot-check; every human correction is written back into the regression set.

---

## 12. Workflows — All Perspectives

**12.0 End user — Ask (conversational, added):** type a free-form question, with no document required to be pre-selected → scope-classifier confirms it's contract-related and detects whether the question is portfolio-wide or scoped to one named document → Retriever (same GraphRAG layer as Suggest, querying across all document nodes under the tenant by default) pulls relevant clause nodes from however many contracts match → answer streams back with inline citations to **document name + page/section** for every claim → RAGAS scores faithfulness in the background → if no supporting clause exists anywhere in the tenant's graph, the agent explicitly says so instead of guessing → can be used before, after, or independently of Detect/Suggest/Fix & Learn, since it only reads the graph and never writes to it, and works identically regardless of when each underlying document was originally uploaded.

**12.0b End user — Ask, chat-triggered edit request (added):** type an edit instruction naming an existing document (e.g. *"Edit the Acme MSA — change the liability cap to $2M"*) → scope-classifier detects this is an edit instruction, not a question → the document is located by name in the tenant's graph (no re-upload needed) → the request is handed to the **Suggest agent** (Section 4, Agent 2) as a new entry point, running the same Retriever → Contrarian → Judge → Negotiation Twin pipeline used for Detect-originated findings → a drafted redline + negotiation memo is shown in-app → the draft enters the **same mandatory human approval queue** as every other redline (Section 12.6) → only after explicit human approval does the Fix & Learn Executor write anything into the real document via MCP. A chat instruction can request a draft; it cannot cause a file edit on its own.

**12.1 End user — Detect only:** upload contract → mode selector routes to Detect subgraph → LlamaParse ingest → PydanticAI validation → Neo4j graph write → regulatory cross-check → severity-scored risk report returned.

**12.2 End user — Detect + Suggest:** as above, then findings pass to Suggest subgraph → Retriever → Contrarian → Judge → Negotiation Twin → redlines + memo shown in-app; no document touched.

**12.3 End user — Full pipeline:** as above, then redline sent to approval queue → reviewer accepts/rejects/edits → on accept, Executor agent writes via MCP into the real document → Visual Diff/QA agent checks formatting → outcome writes back into `playbook_versions` and eval harness.

**12.3b End user — Restore a prior version (added):** a client later determines an approved edit was wrong → requests a restore to a specific prior version, with a required justification → request enters the same approval queue as any other edit → only a reviewer/admin role can approve it → on approval, the Executor writes the restored content back into the real document via MCP, logged in `audit_log` and `document_versions` exactly like a forward edit → if the same document accumulates repeated restore requests within a short window, it is flagged for admin review rather than blocked outright.

**12.4 Power user — standalone entry points:** skip straight to Suggest with self-supplied flagged clauses, or straight to Fix & Learn with an already-approved edit (still gated by approval-queue state).

**12.5 System — perpetual monitoring (unattended):** scheduled job ingests regulatory feeds → embeds and diffs against the live graph → auto-generates a Detect-style finding per newly-affected contract → can hand off into Suggest and, after approval, Fix & Learn → dashboard surfaces newly-flagged contracts.

**12.6 Reviewer/Compliance Officer:** opens approval queue ranked by severity/confidence → inspects diff + rationale + confidence → accepts/rejects/edits (immutably logged to `audit_log`) → a rising rejection rate on a clause type surfaces as an independent drift-warning signal.

**12.7 Developer/DevOps (CI/CD):** commit/PR triggers lint + unit tests + a CUAD-based eval gate → merge builds container → staging deploy + smoke tests → production requires a canary gate → monitored rollout with auto-rollback on regression → LangSmith/Prometheus/Sentry feed the audit trail.

**12.8 Grounding & accuracy (continuous, cross-cutting):** every claim must cite a specific Neo4j node/relationship (enforced in PydanticAI schema) — no matching clause triggers explicit abstention, never fabrication; retrieval separately benchmarked offline against CUAD gold labels whenever the graph/embeddings/prompt changes.

---

## 13. Suggested Build Order

1. CUAD extraction + PydanticAI schemas + Neo4j graph write → working **Detect agent**.
2. Add mode-selector/router; ship Detect standalone with its own UI.
3. **Add login page + auth (Auth0/Clerk) + per-tenant encryption keys (KMS)** — build this early, right after Step 2, since every subsequent step (Suggest, Fix & Learn, dashboard, notifications) depends on tenant-scoped requests being available from the JWT.
4. Build GraphRAG retrieval + Contrarian/Judge + Negotiation Twin → **Suggest agent** (chainable or standalone).
5. Build approval-gate UI + MCP write-access + visual diff QA → **Fix & Learn agent** (chainable or standalone).
6. Add the regulatory horizon-scanning background process, feeding into the same three agents.
7. **Add the Ask agent** — wraps the Retriever already built in Step 4 with a chat UI, session state, and streaming; safe to build any time after Step 4 since it only *reads* the graph and adds no write paths, so it cannot conflict with Detect/Suggest/Fix & Learn's logic.
8. **Add the tenant dashboard + real-time notifications** — wraps the `findings`/`redline_suggestions`/`approvals` tables already populated by Steps 1–6 with a UI layer and a notification hook; safe to build any time after Step 5, since it only reads existing tables and adds a side-effect (notify), never a new write path.
9. **Add Redis query-result caching + reverse-index invalidation for the Ask agent, and Celery for background document ingestion** — build after Step 7 (Ask agent) exists, since caching wraps its read path, and the invalidation hook reuses the same write-event pattern as Step 8's notifications.
10. Add the eval harness + observability + learning loop (extended to also score Ask's chat answers, per Step 7).
11. Multi-tenant SaaS wrapper.

### Why Ask does not clash with the other three agents
- **No shared write path** — Ask never calls the Executor/MCP write layer used by Fix & Learn, so there is no risk of a chat answer accidentally modifying a real document.
- **No schema conflict** — its session state lives in new, isolated Postgres tables (`chat_sessions`/`chat_messages`); it doesn't touch `findings`, `redline_suggestions`, or `audit_log`.
- **No model routing conflict** — it uses the same two-tier model routing (small/cheap model vs. Opus-class) already defined for Detect vs. Suggest, just applied to conversational load instead of a new routing scheme.
- **No orchestration conflict** — it's implemented as its own LangGraph subgraph, exactly like Detect/Suggest/Fix & Learn/Horizon-Scanning already are, so the mode-selector router simply gains one more branch rather than needing to be redesigned.

### Why the dashboard/notifications don't clash with anything
See Section 8.3 for the full breakdown — in short: both are read-only consumers of existing tables plus one non-blocking side-effect hook (notify-on-write), so they cannot alter the behavior of Detect, Suggest, Fix & Learn, Horizon-Scanning, or Ask.

### Why caching/scaling doesn't clash with anything
See Section 9.5 for the full breakdown — in short: Redis caching only wraps Ask's read path, invalidation reuses the same write-event hook pattern as notifications, and Celery is scoped strictly to background ingestion, never the live query path — so none of it changes Detect/Suggest/Fix & Learn/Horizon-Scanning/Ask's core logic.

---

## 14. Complete Training Data Topography

Building this system involves fine-tuning/evaluating against specialized legal corpora across five layers. Datasets are separated below into **training data (static, one-time)** vs. **live regulatory feed (constant, ongoing)** — this distinction matters for the build (see Section 16).

| Dataset Category | Objective | Representative Corpora | Agent Application |
|---|---|---|---|
| Foundational Extraction | Spatial awareness, clause boundary detection, entity recognition | CUAD, LexGLUE, ACORD | Base Parsing Pipeline |
| Logical Inference | Entailment mapping, playbook compliance, contradiction detection | ContractNLI, MAUD | Detect Agent, Judge Agent |
| Redlining & Strategy | Rationale generation, fallback drafting, syntactic modification | RedlineBench, Synthetic GPT-4 Data | Suggest Agent, Negotiation Twin |
| Regulatory & Statutory | Horizon scanning, jurisdictional compliance, legal grounding | DPDP Act Corpus, LegiLM, Cambridge Law Corpus | Horizon-Scanning Agent, Contrarian Agent |
| Syllogistic Reasoning | Multi-hop logic, formal legal argumentation | DISC-Law-SFT, JEC-QA, Open-R1 Traces | Adversarial Review Pair, Negotiation Twin |

**Key corpora, in detail:**
- **CUAD** — 510 expert-annotated commercial contracts, 13,000+ labels across 41 clause categories. Trains base parsing/extraction and doubles as the held-out regression suite. *(🇺🇸 US-centric)*
- **LexGLUE** — multi-task legal NLP benchmark (CaseHOLD, EURLEX57K, SCOTUS, etc.), guards against catastrophic forgetting. *(🇺🇸 US-centric)*
- **ACORD** — 126,000+ query-clause pairs, 114 attorney-formulated queries; trains the GraphRAG retrieval layer. *(🇺🇸 US-centric)*
- **ContractNLI** — 607 annotated contracts, Entailment/Contradiction/NotMentioned labels; core engine behind Detect Agent's compliance reasoning. *(🇺🇸 US-centric)*
- **MAUD** — 47,000+ annotations across 152 M&A agreements, from the ABA's Public Target Deal Points Study; trains Negotiation Twin. *(🇺🇸 US-centric)*
- **RedlineBench** — paired original/redlined clauses with rationale; foundational for Suggest Agent's dual output.
- **Synthetic redlining data (GPT-4/LLM distillation)** — used for PEFT/QLoRA fine-tuning of smaller open-source models (e.g., Llama 3.1) for fast per-clause inference (<5s).
- **DPDP Act Corpus (India)** — statutory text (Chapters I–IX), DPDP Rules 2025, compliance checklists; converted into knowledge-graph nodes for Horizon-Scanning Agent. *(🇮🇳 India — regulatory lookup layer only, not clause-reasoning layer)*
- **LegiLM / GDPR data** — GDPR regulation text, annotated data-sharing contracts, privacy policies. *(🇪🇺 EU — regulatory lookup layer only)*
- **Cambridge Law Corpus** (250,000+ UK court cases) and **JEC-QA** (China's judicial exam QA set) — general legal argumentation structure only. *(🇬🇧 UK / 🇨🇳 China)*
- **DISC-Law-SFT** — legal syllogism dataset (premise/law → facts → conclusion); trains Contrarian/Judge agents.
- **Open-R1 synthetic reasoning traces** — step-by-step reasoning with citations, distilled into Negotiation Twin.

---

## 15. Sectors & Contract Domains Covered

PactScan AI is scoped around **legal/regulatory domains and contract types**, not industry verticals.

**By contract type:**
- MSAs (Master Service Agreements)
- DPAs (Data Processing Agreements)
- NDAs (Non-Disclosure Agreements)
- SOWs (Statements of Work) — can silently override MSA terms, a key reasoning test case
- M&A agreements (via MAUD) — deal-point questions, indemnification, reps & warranties
- Amendments/addendums — generated post-signing when new regulation applies retroactively

**By regulatory domain checked against:**

| Regulation | Sector it governs |
|---|---|
| GDPR | EU data privacy (general) |
| DPDP Act | India data privacy (general) |
| HIPAA | Healthcare data privacy (US) |
| SOC 2 | Data security/trust standards (mainly SaaS/tech vendors) |
| EU AI Act | AI systems/algorithmic accountability |
| State-level privacy laws (e.g. CCPA) | US regional data privacy |

**Implicit industry relevance:** tech/SaaS companies, healthcare, any company handling EU or Indian customer data, and companies procuring AI vendor tools.

**Explicitly out of scope:** criminal law, employment/labor law, tax law, IP litigation, real estate/property law, family law, immigration law. This is a **commercial contract compliance tool focused on data privacy and vendor risk**, not a general-purpose legal AI.

**Current implementation scope (narrower than the full design above, by deliberate choice):** the 7-phase build described in this document's companion phase files is scoped specifically to **SaaS/vendor Data Processing Agreements (DPAs), with India's DPDP Act as the primary regulatory ground-truth** and GDPR retained as a secondary regulation to demonstrate the same architecture and clause taxonomy generalize across jurisdictions without modification. This narrowing was a deliberate decision made for build feasibility within a tight timeline, not a change to the underlying architecture — every mechanism described in this document (multi-hop `OVERRIDES` reasoning, the adversarial review pair, bitemporal versioning, Horizon-Scanning) is fully general and was simply demonstrated against one well-chosen domain rather than all of them at once. HIPAA, SOC 2, EU AI Act, and the broader contract-type list above remain the documented, architecturally-supported target state — see Section 18 for the explicit build-vs-designed distinction.

---

### 15.1 Why This Domain — DPDP-Primary, CUAD-Informed, SaaS Vendor DPAs

This subsection makes the domain-narrowing decision explicit and defensible, since it's a deliberate scoping choice worth being able to explain directly:

- **Regulatory ground-truth:** India's **DPDP Act, 2023** is a real, currently-in-force law, with penalties up to ₹250 crore for serious Data Fiduciary violations — a genuine, current compliance stake, not a hypothetical. It is used as the *primary* regulation the system checks against, rather than one of several equally-weighted regulations.
- **Clause taxonomy grounding:** the clause categories used throughout (Limitation of Liability, Data Processing, Confidentiality, Termination, etc.) are informed by **CUAD (Contract Understanding Atticus Dataset)** — Hendrycks et al., 2021, a peer-reviewed, widely-cited academic benchmark (510 expert-annotated commercial contracts, 13,000+ labels across 41 categories) used across dozens of subsequent legal-NLP papers (MAUD, LegalBench, ACORD). CUAD's *taxonomy* is used as a naming/organizing reference — its actual contract data is not loaded into or used to train anything in this build (see Section 14 and the "no training occurs" clarification below).
- **Why not a dedicated Indian contract-clause dataset:** as of this build, no large, expert-annotated, CUAD-equivalent dataset exists specifically for Indian commercial contracts (India's mature legal-NLP datasets — ILDC, InLegalBERT, IndianBailJudgments — are predominantly court-judgment/case-law corpora, not labeled contract clauses). Using CUAD's taxonomy as the reference structure, while making DPDP the primary regulatory check, is the most defensible way to combine a mature, citable dataset with India-primary regulatory relevance, given this gap.
- **No model training or fine-tuning occurs anywhere in this build.** The LLM (Google Gemini, see Section 6's Implementation Note) is called off-the-shelf via API for every clause-extraction and compliance-classification task. CUAD informs the taxonomy design by hand; it is never used as a training or fine-tuning dataset. This is stated plainly here because it is easy to conflate "our taxonomy is informed by CUAD" with "our model is trained on CUAD" — they are not the same claim, and only the former is true of this build.
- **Why this domain specifically (not a broader or different narrowing):** SaaS vendor DPAs are a category every data-handling company needs on an ongoing, recurring basis (not a one-time event), and the compliance risk is acute and current — companies are actively navigating DPDP obligations right now, not preparing for a distant future requirement.

---

## 16. Regional Applicability — Clarified

### 16.1 Why this matters
The system is **RAG-based for regulation lookup** (new laws are added as graph nodes and retrieved at query time) but **trained/fine-tuned for clause reasoning** on fixed datasets (CUAD, ContractNLI, MAUD). These two layers generalize to new regions very differently:

| Layer | Mechanism | Generalizes to new regions? |
|---|---|---|
| Regulatory compliance-checking | RAG — looks up regulation text live from the graph | **Yes** — works as long as the region's law text is loaded |
| Document parsing (layout) | General structural skill | Mostly yes — PDFs are PDFs |
| Clause classification (41 categories) | Trained on CUAD (US) | **No** — Indian/other regional contract conventions (e.g., stamp duty, Indian Registration Act language) not represented |
| Compliance reasoning (entailment/contradiction) | Trained on ContractNLI (US) | **No** — doctrinal reasoning (e.g., "consideration," "free consent" under Indian Contract Act 1872) doesn't transfer cleanly |
| Negotiation strategy | Trained on MAUD (US M&A precedent) | **No** — US negotiation norms, not regionally grounded |
| Legal argumentation | Cambridge Law Corpus (UK), JEC-QA (China) | Partial, and not India-specific |

### 16.2 The project's actual built-for region
Based on training data composition, **every dataset that trains the core skills (extraction, reasoning, redlining, negotiation) is US-based.** GDPR and DPDP only train the *regulatory lookup layer*, not the underlying reasoning skill.

> **PactScan AI, as specified, is a US-market contract compliance tool**, with an extensible RAG-based regulatory layer that can ingest and check against non-US frameworks (GDPR, DPDP) — though clause classification and negotiation reasoning accuracy for non-US-style contracts would require dedicated regional fine-tuning data before being production-viable outside the US.

### 16.3 What would be needed for genuine India production-readiness
- **ILDC (Indian Legal Documents Corpus)** — Indian court judgments, for Indian legal NLP tasks
- **Indian Kanoon** dataset/API — Indian case law, to ground legal reasoning
- A hand-labeled set of real Indian commercial contracts, annotated in CUAD-style taxonomy, to fine-tune/eval clause classification against Indian conventions
- Indian Contract Act 1872 + Arbitration & Conciliation Act text added to the regulatory graph (same RAG mechanism as DPDP)

This is documented as **future work**, not part of the current build.

---

## 17. Regulatory Update Feed — MVP Scope (Realistic, Student-Project Scale)

The full vision (Section 3.4 / 12.5) calls for scanning "global regulatory feeds." For an MVP, this is scoped down in *source breadth only* — the architecture, graph-write mechanism, and downstream agent hand-off remain **identical**.

### 17.1 Scope decision
Given the region finding in Section 16, the regulatory feed should prioritize sources **in this order**:

**Primary (matches the trained clause-reasoning skill):**
- US federal: HIPAA, FTC data privacy guidance
- US state privacy laws: CCPA/CPRA (California) and other state laws — frequently updated, good demo material, tracked publicly (e.g., IAPP's state privacy law tracker)
- SOC 2 framework updates (AICPA)

**Secondary (regulatory-lookup layer only — demonstrates architecture generalizes, not full accuracy):**
- GDPR (EU) — source: **EUR-Lex** (official EU law database, stable public web interface, free)
- DPDP Act (India) — source: **MeitY** (Ministry of Electronics & IT) official Gazette text + DPDP Rules 2025 PDF

### 17.2 How "continuous monitoring" is simulated for a demo
1. **Simulated scheduler** — a cron job (or manual trigger button in the demo UI) re-checks the 2–3 source URLs on a schedule (e.g. daily), via LangGraph cron or a simple Python `schedule` script. Proves the mechanism without needing real 24/7 infra.
2. **Change detection** — hash/diff the fetched regulation text against the last stored version. No change → no action (realistic most-days case). Change detected → treated as a new regulation node.
3. **Demo trick for showing it work live** — seed a mock regulation update (e.g., "simulate: India adds a new Section 9A requiring X") and show the system detecting it, diffing against test contracts, and flagging affected ones. Standard practice for demoing monitoring systems; does not misrepresent the architecture.

### 17.3 What stays unchanged from the original architecture
- New regulation nodes are still written into the same bitemporal Neo4j graph (`knownFrom` = when the scraper found it)
- Still auto-diffs against stored test contracts using the same Cypher/GraphRAG traversal
- Still hands off to the same Detect → Suggest → Fix & Learn agents — zero architecture change, only fewer/smaller source feeds
- Production framing is preserved in documentation: *"the production version ingests global regulatory feeds via scheduled jobs (LangGraph cron/Temporal.io); the MVP demonstrates this with 2–3 hand-picked sources."*

---

## 18. Limitations & Future Work (For Report / Pitch Credibility)

Stating limitations explicitly increases technical credibility rather than undermining the pitch.

1. **Regional bias in core reasoning.** Clause classification and compliance-entailment reasoning are trained on predominantly US/UK legal corpora (CUAD, ContractNLI, MAUD, Cambridge Law Corpus). Non-US contracts (India, EU, elsewhere) will see degraded classification accuracy even though regulatory *lookup* (via RAG) works well for any region whose law text is loaded.
2. **No Indian or non-Western case-law corpus in current training data.** Deep legal-reasoning corpora (Cambridge Law Corpus, JEC-QA) are UK/China-specific; there is no equivalent Indian corpus (e.g., ILDC, Indian Kanoon) currently included.
3. **MVP regulatory feed is intentionally narrow.** Full "global regulatory horizon-scanning" is architecturally supported but only demonstrated against 2–3 named regulations (US state privacy law + GDPR + DPDP) due to feasibility constraints — not because the architecture can't scale further.
4. **Simulated vs. true continuous monitoring.** The MVP demo uses a scheduled/simulated scraper against static government sources rather than paid, real-time legal-data APIs (e.g., Thomson Reuters, LexisNexis) that a true production deployment would eventually need for full jurisdictional coverage.
5. **Single-tenant perspective only.** The system currently supports one tenant's own view of a contract — it reads, analyzes, and drafts redlines on behalf of the uploading company. It does not currently support two separate tenants (e.g., a vendor and a client, both using PactScan AI independently) collaborating on the *same* shared contract inside the platform. Every architectural choice made so far — cryptographic per-tenant encryption (Section 7.3), strict internal/external memo separation (Section 3.5), and tenant-isolated graph partitioning (Section 7.1) — was deliberately built around single-tenant isolation, so true cross-tenant collaboration is a distinct, larger design problem rather than a small extension. See the dedicated proposal below.
6. **Out of scope entirely:** criminal law, employment/labor law, tax law, IP litigation, real estate law, family law, immigration law.

**Future work path to broaden regional/legal coverage:**
- Add ILDC + Indian Kanoon for India-specific reasoning
- Add Indian Contract Act 1872 + Arbitration Act to the regulatory graph
- Hand-label a small Indian-contract CUAD-style eval set
- Extend the same fine-tuning pattern to any additional target region as needed

### Future Work Proposal — Cross-Tenant Shared Negotiation Space (not built, proposed only)

**The idea:** when two separate companies are both PactScan AI tenants and are counterparties on the same real-world contract, provide an optional shared workspace where either side can push a proposed edit to a mutually visible, separately secured space, and the other side can respond (e.g., with a fallback clause) — with both sides notified in-app and by email the moment a change is proposed.

**Why this is deliberately scoped as future work, not a current build item:**

This is a different *class* of feature from everything else in this document. Every other addition (Ask agent, dashboard, notifications, caching, chat-triggered edits) was designed to extend a single tenant's experience without crossing the tenant-isolation boundary that the architecture is built around. A shared negotiation space breaks that boundary on purpose, which introduces problems that are qualitatively harder than anything else proposed in this document:

- **Encryption model doesn't extend cleanly.** Per-tenant KMS keys (Section 7.3) exist specifically so no data is readable across tenants. A shared document can't be encrypted under only one side's key; it would need a third encryption domain (e.g., envelope encryption with the shared document's key separately wrapped for each tenant) — a real cryptographic design problem, not a configuration change.
- **No existing concept of a tenant-to-tenant relationship.** The current data model (Section 7.1) only knows about one tenant and its own documents. Supporting this would require a consent/linking mechanism between two tenants, plus a way to verify Company B is genuinely the counterparty named in the contract (not just a same-named or spoofed account) — an identity-verification problem in its own right.
- **Changes what the product fundamentally is.** PactScan AI is currently a single-sided decision-support tool — Detect/Suggest/Fix & Learn all serve the uploading tenant's interests. A shared space turns it into a two-sided negotiation platform, which raises unresolved product questions: whose compliance playbook governs the shared document, is one side's Contrarian/negotiation-memo reasoning ever exposed to the other side, and who holds the canonical "current" version.
- **Liability/confidentiality risk.** The system's existing internal/external output separation (Section 3.5) exists specifically so a tenant's own negotiation strategy (risk tiers, walkaway positions) is never sent to the counterparty. A shared workspace risks quietly undermining that same protection if not designed with extreme care.
- **Limited real-world applicability.** This feature only activates when *both* counterparties happen to use the same platform — realistically a small fraction of real contracts — so the build cost is high relative to how often it would actually be used at this project's current scale.

**Conclusion:** technically feasible, but architecturally heavy enough that it is proposed here only as a roadmap direction — evidence of where the product could evolve (single-tenant tool → two-sided negotiation platform) — rather than committed to the current build scope.

---

## 19. Summary Table — Full Project at a Glance

| Aspect | Answer |
|---|---|
| What it does | Reads contracts, flags compliance risks, drafts fixes, applies approved edits, and continuously re-checks the archive as laws change |
| **Current implementation scope** | **SaaS/vendor Data Processing Agreements (DPAs), India's DPDP Act as primary regulation, GDPR secondary (generalization demo) — see Section 15.1.** All rows below describe the full aspirational design; this row states what the 7-phase build actually targets. |
| Core architecture | 4 agents — Detect, Suggest, Fix & Learn (chainable/standalone) + Ask (conversational, read-only) — plus a background Horizon-Scanning agent, all built on a bitemporal Neo4j knowledge graph |
| Key differentiators | Adversarial review pair, Negotiation Twin, bitemporal graph, perpetual horizon-scanning, mandatory human approval gate |
| Primary trained region (full design) | 🇺🇸 US (clause reasoning, redlining, negotiation) — aspirational; current build uses CUAD as a taxonomy reference only, no training performed (Section 15.1) |
| Secondary region (RAG-only) | 🇪🇺 EU (GDPR), 🇮🇳 India (DPDP) — regulatory lookup only; **in the current build, DPDP is primary, not secondary** (Section 15.1) |
| Contract types covered | MSA, DPA, NDA, SOW, M&A agreements, amendments |
| Regulations covered | GDPR, DPDP, HIPAA, SOC 2, EU AI Act, US state privacy laws |
| Explicitly out of scope | Criminal, employment, tax, IP litigation, real estate, family/immigration law |
| MVP regulatory feed sources | US state privacy trackers (IAPP), EUR-Lex (GDPR), MeitY (DPDP) |
| Tech stack core | LlamaParse, PydanticAI, Neo4j GraphRAG, LangGraph, Google Gemini (local cache + 7-tier model chain + multi-account fallback, 3 accounts — see Section 6's Implementation Note; Claude Agent SDK is the documented aspirational design), MCP, FastAPI (incl. SSE for Ask streaming), Next.js, PostgreSQL |
| Auth & security | Auth0/Clerk login (SSO + MFA), JWT-based tenant scoping, per-tenant KMS encryption keys (at rest), TLS 1.3 (in transit) |
| Dashboard & alerts | Role-based tenant dashboard (portfolio health, findings pipeline, regulatory exposure); real-time in-app + email notifications on every new finding — including background Horizon-Scanning findings on old contracts |
| Scaling & performance | Redis caches Ask agent answers with reverse-index invalidation on document edits/new findings + TTL safety net; Celery handles background bulk-document ingestion, kept off the live query path |
| Chat-triggered edits | Ask agent accepts edit instructions naming an existing document; hands off to Suggest for drafting only — mandatory human approval gate (Section 3.5) still required before any real file is written |
| Document versioning & restore | Every Fix & Learn edit is archived, not overwritten; restoring a prior version is itself an approval-gated action requiring a logged reason and reviewer/admin sign-off, with repeated restores on one document flagged (not blocked) for admin review |
| Build order | Detect → router/UI → Login/Auth/Encryption → Suggest → Fix & Learn (approval gate + MCP) → Horizon-Scanning → Ask agent → Dashboard/Notifications → Eval harness → Multi-tenant SaaS wrapper |
