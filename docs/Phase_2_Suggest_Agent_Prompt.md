# PHASE 2 — Suggest Agent (Redline Drafting, Simplified) — Windows Edition
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, **scoped to SaaS/vendor Data Processing Agreements (DPAs) under India's DPDP Act, 2023 as the primary regulation** (GDPR retained as a secondary regulation demonstrating generalization). This is **Phase 2** of a 7-phase build. Phase 1 (already complete) built the **Detect Agent**: it parses vendor DPAs, writes them into a Neo4j knowledge graph, and produces severity-scored findings by checking clauses against a playbook (narrowed to vendor data-processing concerns) and two regulations (DPDP primary, GDPR secondary), including multi-hop reasoning. It also built `backend\app\llm\client.py`, a provider-agnostic LLM abstraction with three layers: a local response cache (versioned by `LLM_PROMPT_VERSION`, prevents repeat calls on identical prompts), a 7-tier Google Gemini free-tier model chain (`gemini-3.8-flash` → `gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemma-4-31b`), and a multi-account fallback loop (currently 3 Google AI Studio accounts, extensible via a comma-separated `GEMINI_API_KEYS` list) that walks the full 7-tier chain per account before advancing to the next account — all via the Interactions API. Assume this exists and reuse it for every LLM call in this phase. Do not call the `google-genai` SDK directly anywhere in this phase's code. The real `.env` lives only at `backend\.env`.

**What Phase 2 must prove:** given a finding from Detect (or a manually-specified clause), the system can retrieve relevant context from the graph and draft a proposed redline (replacement clause language) with a rationale — **without writing to any real file**. This phase produces a draft only; the human approval gate and actual file writing happen in Phase 3.

**Full architecture note (for context only — simplify per instructions below):** the full design includes four sub-agents — a Retriever, a Contrarian (argues the counterparty's best-case interpretation), a Judge (reconciles into a final recommendation), and a Negotiation Twin (predicts counterparty pushback and drafts a fallback). **For this phase, build only the Retriever + a single drafting LLM call as the required core.** Build the Contrarian/Judge/Negotiation Twin chain only as a stretch goal if time and API quota allow — do not let it block finishing this phase.

---

## WINDOWS NOTE
All commands in this and later phases use `venv\Scripts\Activate.ps1` (PowerShell) to activate the Python virtual environment (folder name `venv`, not `.venv`). Use `curl.exe` explicitly for any manual API testing, not plain `curl` (which is aliased to `Invoke-WebRequest` in PowerShell and behaves differently).

---

## TECH FOR THIS PHASE
- Retrieval: Neo4j Cypher traversal (reuse Phase 1's graph) + vector similarity search — if Neo4j's native vector index isn't already set up, add it now: create a vector index on `Clause.embedding` (generate embeddings via Gemini's embedding model, read from `GEMINI_EMBEDDING_MODEL` in config, default `gemini-embedding-001` — this is a separate, dedicated quota pool from the 7-tier text-generation chain in `app\llm\client.py`, so embedding calls never compete with Detect/Suggest's LLM calls for the same budget — store the result as a property on each `Clause` node from Phase 1, backfill existing clauses if needed).
- Drafting: use `app\llm\client.py`'s `generate_structured()`, prompted with the retrieved context, to produce a proposed redline + short rationale.
- API framework: FastAPI (extend Phase 1's app).

---

## STEP-BY-STEP BUILD INSTRUCTIONS

### 1. Add vector embeddings to existing Clause nodes (`backend\app\agents\suggest\embed_clauses.py`)
- For every `Clause` node written in Phase 1, generate a text embedding of its `raw_text` via Gemini's embedding endpoint (add a `generate_embedding(text: str) -> list[float]` function to `app\llm\client.py` if not already present, keeping the same provider-agnostic pattern) and store it as a property (e.g., `Clause.embedding`).
- Create a Neo4j vector index on this property (`CREATE VECTOR INDEX clause_embeddings ...` — use correct Neo4j 5.x vector index syntax).
- Run this as a one-time backfill script for the 3 existing sample contracts from Phase 1.

### 2. Build the Retriever (`backend\app\agents\suggest\retriever.py`)
Given a `Finding` (from Phase 1's Detect output — clause_id, violated rule/regulation, explanation):
1. Run a vector similarity search to find semantically related clauses across the tenant's graph.
2. Run a Cypher traversal to pull the full relationship context of the flagged clause (what it `OVERRIDES` or is `OVERRIDDEN_BY`, per Phase 1's schema).
3. Pull the exact text of the `PlaybookRule` or `RegulationClause` that was violated.
4. Return this bundled context as a structured object for the drafting step.

### 3. Build the drafting call (`backend\app\agents\suggest\draft_redline.py`)
- Call `generate_structured()` with: the original clause text, the retrieved context from step 2, and the violated rule/regulation text.
- Request a structured output containing: `proposed_clause_text`, `rationale` (2-4 sentences), `confidence` (0-100).
- **Do not let this call write anything to a file.** This function only returns data.

### 4. (STRETCH GOAL — build only if core above is done and stable) Contrarian + Judge pair (`backend\app\agents\suggest\adversarial_review.py`)
- Contrarian: a `generate_structured()` call prompted to argue the *opposite* position — that the original clause is actually fine/defensible from the counterparty's perspective, using the same retrieved context.
- Judge: a second `generate_structured()` call that receives both the original finding's reasoning and the Contrarian's argument, and produces a final confidence-scored recommendation — which may confirm, downgrade, or dismiss the original finding.
- If a finding is dismissed by the Judge, it should still be logged (not silently deleted) with a note explaining why, so the adversarial check is auditable.

### 5. (STRETCH GOAL) Negotiation Twin (`backend\app\agents\suggest\negotiation_twin.py`)
- A `generate_structured()` call prompted to predict likely counterparty pushback on the proposed redline and draft one fallback clause as a pre-approved alternative.

### 6. Build the FastAPI endpoints (`backend\app\api\suggest.py`)
- `POST /api/suggest/from-finding/{finding_id}` — runs Retriever + drafting on an existing Phase 1 finding, returns the proposed redline + rationale (+ adversarial review results if built).
- `POST /api/suggest/standalone` — accepts a manually-specified `contract_id` + `clause_id` + free-text description of the desired change, and runs the same Retriever + drafting pipeline. This proves the "standalone-capable, not just chained from Detect" architecture requirement.
- Store every Suggest output in PostgreSQL in a new `redline_suggestions` table: `id`, `finding_id` (nullable, for standalone requests), `contract_id`, `clause_id`, `proposed_text`, `rationale`, `confidence`, `created_at`.

### 7. Minimal frontend addition (`frontend\app\suggest\page.tsx`)
Extend the Phase 1 findings list page — add a "Suggest Fix" button next to each finding that calls `POST /api/suggest/from-finding/{finding_id}` and displays the proposed redline + rationale inline. No file writing UI yet — that's Phase 3.

---

## TESTS TO WRITE (`backend\tests\test_suggest_agent.py`)
- Test that `POST /api/suggest/from-finding/{finding_id}` on the Phase 1 SOW-override finding returns a redline that plausibly addresses the liability cap issue.
- Test that `POST /api/suggest/standalone` works on a manually-specified clause with no prior Detect finding.
- Test that no file on disk is modified anywhere in this phase — write an explicit test checking file modification timestamps/hashes on the sample contracts before and after calling Suggest endpoints, asserting they are unchanged.
- If Contrarian/Judge was built: test that at least one finding's confidence score changes after adversarial review.

## EXIT CRITERIA FOR THIS PHASE
`POST /api/suggest/from-finding/{finding_id}` and `POST /api/suggest/standalone` both work and return coherent redlines with rationale, stored correctly in `redline_suggestions`. The "no file is ever modified" test passes. Clearly document in `docs\` which stretch goals (Contrarian/Judge/Negotiation Twin) were completed vs. skipped. Do not proceed to Phase 3 until the core Retriever + drafting flow is reliable.
