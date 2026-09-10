# PHASE 1 — Detect Agent (Core Proof of Concept) — Windows Edition
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, **scoped specifically to SaaS/vendor Data Processing Agreements (DPAs) under India's DPDP Act, 2023** — this is not a general-purpose "any contract, any law" tool. This narrower, domain-specific scope is a deliberate project decision, not a limitation to work around: DPDP is the **primary** regulation checked (GDPR is retained as a secondary regulation specifically to demonstrate the architecture generalizes across jurisdictions, not as an equal focus). The clause taxonomy used throughout this build is informed by **CUAD (Contract Understanding Atticus Dataset)** — a peer-reviewed, widely-cited academic benchmark (Hendrycks et al., 2021; 510 expert-annotated commercial contracts, 13,000+ labels across 41 categories) — used here as a *taxonomy reference* for naming/organizing clause categories, not as training data or a dataset actually loaded into the system.

This is **Phase 1** of a 7-phase build. Phase 0 (already complete) set up a monorepo with `backend\` (FastAPI + Neo4j + PostgreSQL + Redis via Docker Compose) and `frontend\` (Next.js + TypeScript). Assume that scaffold exists and is running. The real `.env` file lives at `backend\.env` — this is the only place environment variables are read from; never create or reference a root-level `.env`.

**What Phase 1 must prove:** the system can ingest a vendor DPA, parse it in a layout-aware way, extract structured clauses, write them into a Neo4j knowledge graph with explicit relationships (critically, relationships that let one clause be understood in light of another — e.g., a later document's clause overriding an earlier one), and check those clauses against both an internal compliance playbook (scoped to vendor data-processing concerns) and two loaded regulations (DPDP primary, GDPR secondary), producing a severity-scored risk report with exact page/clause citations. This is the single most important phase — every later phase depends on this graph and this reasoning working correctly.

**Do NOT build in this phase:** redline drafting (Phase 2), any file writes (Phase 3), chat/Q&A (Phase 4), login/dashboard (Phase 5), or the regulatory horizon-scanning background job (Phase 6). Detect only ever reads and reports — it never modifies a document.

---

## LLM PROVIDER — Google Gemini, via a provider-agnostic abstraction with response caching, a 7-tier model chain, and multi-account fallback (build this from the start)

**Do not call the `google-genai` SDK directly from multiple files.** Build a single abstraction layer first, with three layers checked in this exact order for every call: **cache → model tier chain → account chain.**

### Layer 1 — Local response cache (checked first, before any API call)

**Why this exists:** during iterative development, the same 3 static fixture contracts get re-processed identically on every restart — same clause text, same rule/regulation checks. Without caching, this burns real API quota on requests that already have a known-correct answer. This is the single most effective quota-conservation measure — implement it first, before the multi-account logic below, since a cache hit means the account/tier logic never even runs.

- Create `backend\app\llm\cache.py` containing:
  - `def compute_cache_key(prompt: str, schema_name: str, prompt_version: str) -> str` — returns a stable hash (e.g., SHA-256) of `prompt + schema_name + prompt_version` concatenated together.
  - `def get_cached_response(cache_key: str) -> str | None` — reads from a local file-based cache (one JSON file per cache key, stored under `LLM_CACHE_DIR` from config, default `.llm_cache/`) — return `None` on a miss.
  - `def set_cached_response(cache_key: str, response_text: str) -> None` — writes the response to the cache.
  - Respect `LLM_CACHE_ENABLED` from config (default `true`) — when `false`, skip the cache entirely (useful for a final live-accuracy check where you deliberately want fresh answers).
- **The versioned cache key is critical — read this carefully:** the cache key must include `LLM_PROMPT_VERSION` from config (default `v1`), not just the clause/rule text. This exists specifically so that if a prompt template, schema, or extraction logic changes during development, the developer bumps `LLM_PROMPT_VERSION` in `.env`, and every old cache entry automatically becomes a miss — forcing fresh calls under the new logic. Without this, a cached answer computed under old, now-changed logic could be silently served after a code update, which would be a real correctness bug, not just a caching inconvenience.
- Add `.llm_cache/` to `.gitignore` — this is a local dev artifact, never committed.

### Layer 2 — 7-tier model fallback chain (per account)

- Create `backend\app\llm\client.py` containing:
  - `async def generate_structured(prompt: str, schema: Type[BaseModel], system_prompt: str = None) -> BaseModel` — takes a Pydantic schema, returns a validated instance.
  - `async def generate_text(prompt: str, system_prompt: str = None) -> str` — for simpler, non-structured calls if any are needed.
  - **Both functions check the cache (Layer 1) first.** On a cache hit, parse and return the cached response immediately — no API call is made at all. On a miss, proceed to Layer 2/3 below, and on success, write the result to the cache before returning.
  - **Use Gemini's Interactions API** (via `client.interactions.create(...)`), not the older `generate_content` call style. For structured output, pass `response_format={"type": "text", "mime_type": "application/json", "schema": YourPydanticModel.model_json_schema()}` and parse the result with `YourPydanticModel.model_validate_json(interaction.output_text)`. This is Gemini's equivalent of Claude's tool-use.
  - The 7-tier model chain, read from config in this exact priority order:
    1. `GEMINI_MODEL_TIER_1` (default `gemini-3.8-flash`) — try first, newest and highest-quality of the available free-tier options
    2. `GEMINI_MODEL_TIER_2` (default `gemini-3.7-flash`)
    3. `GEMINI_MODEL_TIER_3` (default `gemini-3.6-flash`)
    4. `GEMINI_MODEL_TIER_4` (default `gemini-3.5-flash`)
    5. `GEMINI_MODEL_TIER_5` (default `gemini-3.5-flash-lite`) — much higher daily cap, use once Tiers 1-4 are exhausted
    6. `GEMINI_MODEL_TIER_6` (default `gemini-3.1-flash-lite`) — separate quota pool from Tier 5
    7. `GEMINI_MODEL_TIER_7` (default `gemma-4-31b`) — final high-volume safety net, for the current account

### Layer 3 — Multi-account fallback (wraps Layer 2)

**Why this exists:** even the full 7-tier chain under one Google AI Studio account has a finite total daily ceiling. The developer has (or will have) 3 separate Google AI Studio accounts, each with its own independent set of the same 7 quota pools — tripling total effective capacity.

- Read `GEMINI_API_KEYS` from config as a **comma-separated list**, parsed into a Python list of strings (e.g., `["key1", "key2", "key3"]`). This list is intentionally extensible: **adding a 4th or 5th account later requires only appending another key to this comma-separated `.env` value — no code change.** Do not hardcode a fixed number of accounts anywhere in the logic; iterate over however many keys are present in the parsed list.
- **Combined fallback algorithm, for every `generate_structured()`/`generate_text()` call on a cache miss:**
  ```
  for account_index, api_key in enumerate(GEMINI_API_KEYS):
      for tier_index, model_name in enumerate(MODEL_TIER_CHAIN):
          try:
              result = call_gemini(api_key=api_key, model=model_name, ...)
              log.info(f"Answered by Account {account_index+1}, Tier {tier_index+1} ({model_name})")
              cache_response(...)
              return result
          except QuotaOrRateLimitError:
              continue  # advance to next tier under this same account
          # any other exception type should raise immediately, not be caught here
      # only reached if all 7 tiers under this account raised QuotaOrRateLimitError
      log.warning(f"All 7 tiers exhausted for Account {account_index+1}, advancing to next account")
  raise AllLLMTiersExhaustedError("All tiers exhausted across all configured accounts")
  ```
  This is the exact intended shape — full tier chain per account, only advancing accounts once every tier under the current one is exhausted, not the reverse (do not try Tier 1 across all accounts before trying Tier 2 — that would waste the quality-first ordering of the tier chain itself).
- **Only quota/rate-limit-specific errors (HTTP 429, or the SDK's equivalent quota-exceeded exception type) advance the loop.** Any other exception type (malformed request, invalid schema, network timeout unrelated to quota) must raise immediately and not be silently absorbed — blanket-catching all exceptions here would mask real bugs as if they were quota issues.
- **Log the full resolution path for every call** — which account and which tier actually answered — exactly as shown in the pseudocode above. This is genuinely useful signal during development: seeing calls consistently resolving on Account 2/Tier 5, for example, tells you Account 1 is exhausted and you're already partway into your total capacity, well before you'd otherwise notice.

### Configuration and other notes

- Read all tier model names, `GEMINI_API_KEYS`, `GEMINI_EMBEDDING_MODEL` (default `gemini-embedding-001`, used later in Phase 2 — uses only the *first* key in `GEMINI_API_KEYS` by default, no dedicated multi-account fallback for embeddings in this phase since embedding calls are low-volume relative to the text-generation chain), and the cache settings (`LLM_CACHE_ENABLED`, `LLM_CACHE_DIR`, `LLM_PROMPT_VERSION`) from `backend\.env` via `app\config.py` — never hardcode any of these inline elsewhere in the codebase.
- Gemini 3-series models are generally recommended to run at their **default temperature (do not force `temperature=0`)**, since Gemini 3's reasoning is optimized around its default settings — if you need more deterministic behavior for testing, control this via the mocking strategy in tests (see below) rather than forcing an unusual temperature setting on the live model.
- `gemini-3.1-pro-preview` (read from `GEMINI_MODEL_IF_BILLING_ENABLED` in config) is not part of the active tier chain — it exists only as a documented, easy manual upgrade path (a single config change) if billing is ever enabled on any of the AI Studio accounts later.
- Every agent function in this phase (ingestion, override detection, NLI classification) must call `generate_structured()` or `generate_text()` from this module — never instantiate a Gemini client directly inside `ingest.py`, `detect_agent.py`, or `graph_writer.py`. This keeps a future provider, model, or account-count change a one-file change, not a scattered rewrite.

---

## TECH FOR THIS PHASE
- Document parsing: **LlamaParse** (via the current `llama-cloud` Python package — check current API, as this package has had breaking changes; use `client.parsing.parse(...)` with markdown output, accessing per-page text via the result's markdown pages).
- Structured validation: **Pydantic** models — validate every extracted clause against a schema; if a clause doesn't clearly fit a category, mark it `confidence: low` rather than guessing.
- Graph database: **Neo4j** (already running via Phase 0's docker-compose), accessed via the official `neo4j` Python driver, using **Cypher** queries.
- Compliance reasoning: use the `app\llm\client.py` abstraction (Gemini underneath) prompted to perform NLI-style classification — for each clause, classify against a rule as `ENTAILS` (satisfies), `CONTRADICTS` (violates), or `NEUTRAL` (doesn't address it).
- API framework: FastAPI (already scaffolded).

---

## STEP-BY-STEP BUILD INSTRUCTIONS

### 1. Sample data — create 3 synthetic test contracts, generated programmatically
Do not check in binary PDF files. Instead, create `backend\tests\fixtures\generate_fixtures.py` using the `reportlab` package (add `reportlab==4.2.5` to `requirements.txt` — a stable, current version; verify latest compatible at install time if this specific patch is unavailable) to generate 3 synthetic PDFs at test time, and a `conftest.py` `autouse` session fixture that ensures these PDFs exist before any test runs. **All three fixtures should read as vendor DPAs/MSAs for a fictional Indian SaaS company (e.g., "NovaHealth Technologies Pvt Ltd") contracting with a fictional cloud/data-processing vendor — use INR amounts and Indian-company-style naming, not generic global placeholders:**

- **`contract_a_conflict.pdf`** — a fictional MSA + SOW between the Indian SaaS company and a vendor, containing:
  - A Limitation of Liability clause on page 1 stating a cap of ₹80,00,000 (80 lakh)
  - An SOW Addendum on page 2 stating: "Notwithstanding the MSA, liability for data-breach events under this SOW shall not exceed ₹4,00,00,000 (4 crore)"
  - This is the deliberate multi-hop test case — Detect must catch that the SOW clause overrides the MSA clause specifically for data-breach events.
- **`contract_b_regulation_gap.pdf`** — a Data Processing Agreement containing a vague consent clause ("Vendor shall obtain appropriate consents") with no specific mention of minors'/children's data or verifiable parental consent — deliberately designed to be flagged against **both DPDP Section 9** (primary) **and GDPR Article 8** (secondary, demonstrating the taxonomy generalizes — see regulation seeding below).
- **`contract_c_clean.pdf`** — a fully compliant vendor DPA (explicit governing law, an acceptable liability cap, timely breach notice, audit rights, no children's-data processing, clear data-localization/cross-border transfer terms) with no planted issues, used to verify the system does not produce false positives.

### 2. Define the Pydantic schema for an extracted clause (`backend\app\models\clause.py`)
- **`ClauseType`** enum — a **taxonomy narrowed to vendor DPA/MSA-relevant categories, informed by CUAD's clause taxonomy** (CUAD's naming conventions as a reference only — not CUAD's full 41 categories, and not CUAD's actual contract data): `LIMITATION_OF_LIABILITY`, `DATA_PROCESSING`, `DATA_LOCALIZATION_CROSS_BORDER_TRANSFER`, `TERMINATION`, `TERMINATION_FOR_CONVENIENCE`, `CONFIDENTIALITY`, `GOVERNING_LAW`, `INDEMNIFICATION`, `AUDIT_RIGHTS`, `BREACH_NOTIFICATION`, `SUBPROCESSOR_OBLIGATIONS`, `OTHER`. This is intentionally narrower than a general-purpose contract taxonomy (dropped: `NON_COMPETE`, `IP_OWNERSHIP`, `INSURANCE`, `PAYMENT_TERMS`, `DISPUTE_RESOLUTION` — not relevant to the vendor-DPA compliance focus of this build) — this narrowing is a deliberate scope decision, not an oversight.
- **`ConfidenceLevel`** enum: `high`, `medium`, `low`.
- **`ExtractedClause`** model: `clause_id`, `contract_id`, `clause_type`, `page_number`, `section_header`, `raw_text`, `confidence`.
- **`Finding`** model: `finding_id`, `clause_id`, `clause_type`, `page_number`, `section_header`, `severity` (`HIGH`/`MEDIUM`/`LOW`), `rule_or_regulation_violated`, `explanation`, `confidence`, `override_chain` (list of clause IDs for multi-hop tracing).
- **`DetectReport`** model: `contract_id`, `filename`, `findings` list, `total_findings`, `timestamp`.

### 3. Build the ingestion pipeline (`backend\app\agents\detect\ingest.py`)
- Accepts a file path, calls LlamaParse to get structured, layout-aware output (preserving page numbers and section headers).
- Passes the parsed output to `generate_structured()` (from `app\llm\client.py`) to extract clauses matching the `ExtractedClause` schema.
- Any clause the model isn't confident about must be returned with `confidence: low`, never silently dropped or guessed.

### 4. Build the Neo4j graph write (`backend\app\agents\detect\graph_writer.py`)
Define and create these node types and relationships in Neo4j (write the Cypher yourself, matching this schema):
- **Nodes:** `(:Contract {id, filename, tenant_id, upload_date})`, `(:Clause {id, contract_id, clause_type, page_number, section_header, raw_text, confidence})`, `(:PlaybookRule {id, rule_text})`, `(:RegulationClause {id, regulation_name, section, text})`
- **Relationships:** `(:Clause)-[:BELONGS_TO]->(:Contract)`, `(:Clause)-[:OVERRIDES]->(:Clause)` (detect via keyword heuristics — "notwithstanding", "supersedes", "in lieu of" — plus an LLM confirmation call via `generate_structured()` asking "does clause X override, amend, or reference clause Y?"), `(:Clause)-[:VIOLATES]->(:RegulationClause)`, `(:Clause)-[:CONTRADICTS]->(:PlaybookRule)`
- Tenant scoping: every node must carry a `tenant_id` property; for Phase 1, hardcode `tenant_id = "demo_tenant"` (multi-tenancy is built properly in Phase 5) — but write every Cypher query filtered by `tenant_id` regardless, so upgrading to real multi-tenancy later is a small change, not a rewrite.

### 5. Seed the compliance playbook and both regulations (`backend\app\agents\detect\seed_data.py`)
- **Playbook:** 8 hardcoded `PlaybookRule` nodes, narrowed specifically to **vendor DPA/data-processing concerns** (not generic contract-law rules): breach notification window (e.g., within 72 hours of discovery), liability cap threshold for data-breach events, mandatory DPA fields (processing purpose, data categories, retention period), verifiable parental/children's-data consent requirement, subprocessor notification and approval requirement, data localization/cross-border transfer restriction, data deletion/return obligation on termination, audit rights for the data principal's company.
- **DPDP (India) — primary regulation:** load 3 `RegulationClause` nodes — Section 9 (verifiable parental consent), Section 4 (grounds for processing), Section 8 (data fiduciary obligations, including breach notification).
- **GDPR — secondary regulation, demonstrates generalization:** load 2 `RegulationClause` nodes — Article 8 (children's consent), Article 6 (lawful basis).
- **This DPDP-primary, GDPR-secondary setup is intentional** — DPDP is the regulatory ground-truth this build is scoped around; GDPR is retained specifically to demonstrate the same architecture and taxonomy generalize to a second jurisdiction without modification. `contract_b_regulation_gap.pdf`'s vague consent clause is designed to fail both regulations independently.
- Seed idempotently via Cypher `MERGE` (not `CREATE`), called during FastAPI startup lifespan event.

### 6. Build the multi-hop traversal + compliance check (`backend\app\agents\detect\detect_agent.py`)
For every clause of a newly-ingested contract:
1. Run a Cypher query that traverses `OVERRIDES` relationships up to 3 hops deep (`OVERRIDES*1..3`) to find the *effective* current meaning of a clause (not just its literal isolated text).
2. For the effective clause text, call `generate_structured()` to run an NLI check against every relevant `PlaybookRule` and both regulations' `RegulationClause` nodes — classify as `ENTAILS`/`CONTRADICTS`/`NEUTRAL`.
3. Any `CONTRADICTS` result, or any `NEUTRAL` result where the rule is clearly relevant (e.g., a DPA being checked against a data-consent rule), becomes a **Finding**.
4. Severity mapping: regulation `CONTRADICTS` → `HIGH`; playbook `CONTRADICTS` → `MEDIUM`; relevant `NEUTRAL` gap → `MEDIUM`/`LOW`; irrelevant `NEUTRAL` → skip, no finding.
5. Persist findings as `Finding` nodes in Neo4j with `HAS_FINDING` edges, and write `VIOLATES`/`CONTRADICTS` edges back to the graph for future retrieval (this matters for Phase 2's Retriever).

### 7. Build the FastAPI endpoint (`backend\app\api\detect.py`)
- `POST /api/detect` — accepts a file upload, runs the full pipeline (ingest → graph write → compliance check), returns a JSON risk report: list of findings, each with `clause_type`, `page_number`, `section_header`, `severity`, `rule_or_regulation_violated`, `explanation`, `confidence`, `override_chain`.
- `GET /api/detect/{contract_id}` — returns the previously-computed findings for an already-ingested contract (don't force re-running the whole pipeline every time).

### 8. Minimal frontend page (`frontend\app\detect\page.tsx`)
A simple upload form (drag-and-drop or file picker) that calls `POST /api/detect` and renders the returned findings as a list, each showing severity (color-coded: red=HIGH, amber=MEDIUM, sky=LOW), page number, section, explanation, and an override-chain indicator when a multi-hop conflict is present. This does not need to be polished — Figma-designed UI comes in Phase 5.

---

## TESTS TO WRITE (`backend\tests\test_detect_agent.py`)

Mock the LLM client (`app\llm\client.py`) and LlamaParse by default for fast, deterministic test runs — use a `@pytest.mark.live` marker for a small set of tests that call the real Gemini/LlamaParse APIs, so routine test runs don't burn API quota.

- Test that `contract_a_conflict.pdf` produces a finding that correctly identifies the SOW clause overriding the MSA clause (assert the finding references both page 1 and page 2, and `override_chain` is populated).
- Test that `contract_b_regulation_gap.pdf` produces two separate HIGH-severity findings — one citing DPDP Section 9 (primary), one citing GDPR Article 8 (secondary, demonstrating generalization).
- Test that `contract_c_clean.pdf` produces **zero** findings (false-positive check).
- Test that re-running Detect (via the `GET` endpoint) on the same contract twice produces identical JSON (idempotency check).
- Test that every finding includes a page number that is a positive integer.
- Test that the 7-tier model fallback logic in `app\llm\client.py` triggers correctly: mock Tier 1 to raise a quota/rate-limit error and assert the call correctly advances to and succeeds on Tier 2, with the account and tier number logged. Also test that a non-quota error (e.g., a malformed request) does NOT trigger fallback advancement — it should raise immediately, since blanket-catching all errors would mask real bugs.
- Test the multi-account fallback specifically: mock all 7 tiers under Account 1 to raise quota errors, and assert the client correctly advances to Account 2's Tier 1 (not, for example, skipping straight to a later tier) and succeeds there.
- Test the cache layer: call `generate_structured()` twice with identical prompt + schema + `LLM_PROMPT_VERSION`, and assert the underlying `call_gemini` function is only invoked once (the second call must be served entirely from cache — mock/spy on the API call function to confirm this).
- Test cache invalidation via prompt versioning: call once with `LLM_PROMPT_VERSION=v1`, then call again with the identical prompt but `LLM_PROMPT_VERSION=v2`, and assert the API is called again (proving the version bump correctly forces a fresh call rather than serving a stale cached answer).

## EXIT CRITERIA FOR THIS PHASE
All mocked tests pass, including the new cache and multi-account fallback tests. The `@pytest.mark.live` tests pass against real Gemini + LlamaParse calls (using `curl.exe`, not plain `curl`, for any manual PowerShell verification). You can run `POST /api/detect` on all 3 sample contracts via the frontend or curl.exe and get correct, citation-accurate results every time. Confirm via Neo4j Browser (`http://localhost:7474`) that the `OVERRIDES` relationship and both regulation node sets exist as expected. **Also confirm empirically:** run the same contract through `POST /api/detect` twice in a row and check the logs — the second run's LLM calls should show cache hits (no new "Answered by Account X, Tier Y" log lines for identical clause/rule pairs), proving the cache is actually intercepting repeat calls, not just present in code but unused. Do not proceed to Phase 2 until this is true.
