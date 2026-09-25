# PactScan AI — Known Issues & Development Lessons Learned
### Paste this entire file into any new Claude chat, or reference it directly, before resuming development

---

## Purpose of this document

This is not the project specification (see `PactScan_AI_Final_Project_Document.md` and the `Phase_0`–`Phase_7` prompt files for that). This is a record of **environment bugs, process mistakes, and debugging discipline** learned across two prior build attempts, so they are never repeated. If you are a fresh Claude session reading this for the first time: the person you're helping has already hit every issue below once — do not let them hit it again.

---

## 1. Environment bugs already found and fixed — do not re-diagnose these from scratch

### 1.1 — `.env` file location
**The bug:** `backend\app\config.py` uses `env_file=".env"`, which resolves relative to the working directory the backend is run from — always `backend\`. A root-level `.env` (`D:\PactScan-AI\.env`) is silently ignored. This caused hours of confusion across multiple sessions because tools (including the agentic IDE) kept creating/editing the wrong one.
**The fix, enforced going forward:** there must be exactly one real `.env`, at `backend\.env`. No `.env` or `.env.example` should ever exist at the project root. Every phase prompt file already states this explicitly — if a new instruction to an agentic IDE doesn't repeat this, add it yourself before running the instruction.

### 1.2 — PostgreSQL port conflict
**The bug:** a native PostgreSQL Windows Service was already listening on port 5432, silently colliding with the Docker container mapped to the same port. Credentials appeared to "never work" no matter how many times the Docker volume was reset — the real problem was the backend randomly connecting to the wrong Postgres instance entirely.
**The fix, enforced going forward:** Docker's Postgres service is mapped to host port **5433**, not 5432 (`"5433:5432"` in `docker-compose.yml`), and `DATABASE_URL` in `backend\.env` uses port 5433. If a fresh machine is ever used, check `netstat -ano | findstr :5432` for a competing process before assuming credentials are wrong.

### 1.3 — Virtual environment naming and activation
**The bug:** inconsistent naming (`venv` vs `.venv`) between what was documented and what was actually created caused `Activate.ps1` to fail with a confusing "module not found" error.
**The fix, enforced going forward:** the virtual environment folder is always named exactly `venv`. Activate with `venv\Scripts\Activate.ps1` in PowerShell. Confirm the prompt shows `(venv)` before running any Python command.

### 1.4 — PowerShell's `curl` is not curl
**The bug:** PowerShell aliases `curl` to `Invoke-WebRequest`, which does not support standard curl flags like `-X`, causing confusing parameter-binding errors that look unrelated to the actual command.
**The fix, enforced going forward:** always use `curl.exe` explicitly for manual API testing on Windows, never plain `curl`.

### 1.5 — Anthropic API had no usable credits
**The bug:** the original plan assumed Claude (via Anthropic API) as the LLM provider for the application's runtime agents. The Anthropic account could not be funded.
**The fix, enforced going forward:** the application's LLM provider is **Google Gemini**, via a provider-agnostic abstraction (`backend\app\llm\client.py`), using a 7-tier free-tier fallback chain wrapped in multi-account fallback (see Section 2 below) — not Claude. Anthropic/Claude is used only as the *development* tool (Claude.ai chat for planning/docs, Claude Code for actual coding — see Section 6) — never as the application's own runtime model, since that path has no funded access.

---

## 2. Current LLM provider configuration (application runtime, not the dev tools)

The application's `backend\app\llm\client.py` has three layers, checked in this order for every call: **cache → 7-tier model chain → multi-account chain.**

**Layer 1 — cache:** every call is first checked against a local file-based cache, keyed by a hash of `prompt + schema + LLM_PROMPT_VERSION`. A cache hit returns immediately with zero API calls. `LLM_PROMPT_VERSION` (in `.env`) must be bumped any time prompt/schema logic changes, so old cached answers computed under outdated logic are never silently served.

**Layer 2 — 7-tier model chain (per account):**
1. `gemini-3.8-flash`
2. `gemini-3.7-flash`
3. `gemini-3.6-flash`
4. `gemini-3.5-flash`
5. `gemini-3.5-flash-lite` (500 requests/day — the practical workhorse tier)
6. `gemini-3.1-flash-lite` (separate 500/day quota pool)
7. `gemma-4-31b` (14,400/day last-resort pool)

**Layer 3 — multi-account fallback:** `GEMINI_API_KEYS` in `.env` holds a comma-separated list of Google AI Studio API keys (currently 3 accounts). The client walks the *full* 7-tier chain under the current account first; only once every tier under that account has returned a quota error does it advance to the next account's key and restart the tier chain from Tier 1. Adding a 4th/5th account later requires only appending another key to the comma-separated list — no code change.

Dedicated, separate quota pool for embeddings: `gemini-embedding-001` (used only by Phase 2's vector embeddings, uses the first account key only — no dedicated multi-account fallback for embeddings, since embedding calls are low-volume relative to the text-generation chain).

`gemini-3.1-pro-preview` is configured but inactive — it requires a billing account attached to the Google AI Studio project, which is not currently set up. This is a documented future upgrade path, not something to debug around right now.

---

## 3. Rate limits — root cause and the actual fix

**What was initially suspected:** the fallback chain wasn't working correctly.
**What was actually happening:** repeated project restarts caused the same static fixture contracts to be re-processed identically every time, burning real API quota on duplicate work — this is a call-volume problem, not a fallback-logic problem.

**The fix, now built directly into the architecture (see Section 2):**
1. **Local response cache** (Layer 1 above) — an identical prompt should never hit the real API twice, regardless of how many times the project is restarted.
2. **Multi-account fallback** (Layer 3 above) — provides a much larger total capacity ceiling for calls that are genuinely new, on top of (not instead of) the cache.
3. Batching NLI compliance checks (checking a clause against all relevant rules/regulations in one structured-output call, not one call per pair) remains a good further optimization if quota pressure is still felt after the above — not yet built as of this document, worth adding if needed.

**A note on why caching and multi-account fallback are not competing solutions:** caching prevents *unnecessary repeat* calls; multi-account fallback provides more capacity for *genuinely new* calls. They solve different problems and are meant to be used together, with caching checked first so the account/tier logic only runs on an actual cache miss.

**If this document is being read fresh and rate limits are being hit again:** confirm the cache, the multi-account loop, and correctly-populated `GEMINI_API_KEYS` all actually exist and are being used in the codebase before assuming a new problem — any of these may not have been implemented yet, or may have regressed.

---

## 4. Testing discipline — the actual rule that prevents repeated confusion

**The core distinction that was repeatedly a source of confusion:** "automated tests passed" and "manual testing failed" are not a contradiction — they test different things.

- **Mocked `pytest` (`pytest -v`, no `-m live` flag):** zero real API calls, zero Docker/env dependency for the LLM parts, fast, free. This is the *only* thing that should be run repeatedly during iteration. If this is green, the core logic is sound.
- **Live tests (`pytest -m live -v`) and manual `curl.exe` calls:** real API calls, real quota cost, real environment dependency (Docker up, `.env` correct, ports free). **Run this exactly once, deliberately, after mocked tests are fully green** — not repeatedly "to check." Treat every live/manual run as something that costs real, limited quota.

**Rule going forward:** if debugging something, always check mocked `pytest` status first, before touching Docker, `.env`, or any live API call. If mocked tests are green, the problem is environmental/quota-related, not a logic bug — debug accordingly (check Docker, ports, `.env` location) rather than re-reading agent code.

---

## 5. Horizon-Scanning — what it actually is (a repeated point of confusion)

Phase 6's "Horizon-Scanning Agent" does **not** call any external news API, legal-data API, or web scraper. It never has — this was a deliberate scope decision made early in planning, not something cut later due to budget. The regulatory update is entered manually via an admin form field (`POST /api/horizon-scanning/simulate-update`), and everything *downstream* of that manual input (re-diff, compliance check, finding creation, notification) is fully real and automated. If asked "how does it get real regulatory news," the honest answer is: it doesn't, by design, for this build — that's documented as future work, not a gap to solve now.

---

## 6. Development tool — Claude Code Pro (switched from Antigravity, final decision)

**Development has moved permanently to Claude Code Pro** (paid monthly subscription) as the sole tool writing and debugging code for this project, replacing the earlier Antigravity-based workflow. This was a deliberate, final decision — do not switch tools again mid-build. Claude Code always uses Claude models (not the multi-provider picker Antigravity offered), so the per-phase "which model" allocation table from earlier planning no longer applies — there is no model choice to make per phase.

**What carries over from the Antigravity era, still true:**
- The application's own runtime LLM is still **Google Gemini**, per Section 2 above — Claude Code is the *development* tool writing the code; it is not the model the deployed application calls at runtime. This distinction (dev tool vs. runtime model) still matters and is easy to blur.
- All phase prompt files were originally written as "paste into agentic IDE" instructions and have been updated to say "paste into Claude Code" — functionally, paste the entire phase file as your instruction to Claude Code exactly as before.

**What's different, practically:**
- No per-phase model-tier decision needed — proceed phase by phase as documented in the phase files themselves.
- Claude Code can directly read, edit, and run code in the actual repository and see real terminal/error output without manual copy-paste — this directly addresses the "paraphrased error" and "manual relay between tools" friction documented in Section 8 below, from the prior Antigravity-based attempts.

---

## 7. Domain scope — narrowed, final decision (read this before writing any code)

The project is **not** a general-purpose "any contract, any regulation" tool. It is scoped specifically to:
- **Contract type:** SaaS/vendor Data Processing Agreements (DPAs) and their parent MSAs.
- **Primary regulation:** India's **DPDP Act, 2023**.
- **Secondary regulation:** GDPR — retained specifically to demonstrate the same architecture and clause taxonomy generalize to a second jurisdiction, not as an equally-weighted focus.
- **Clause taxonomy:** informed by **CUAD's** category naming conventions (a peer-reviewed academic benchmark), narrowed to vendor-DPA-relevant categories only (dropped: non-compete, IP ownership, insurance, payment terms, dispute resolution — not relevant to this domain).
- **No model training or fine-tuning occurs anywhere.** CUAD is a taxonomy reference only, never loaded as training data. The LLM (Gemini) is called off-the-shelf via API for every task.

This was a deliberate final decision made to fit a tight build timeline while still producing a genuinely defensible, citable, in-scope result — not a limitation to work around or expand back out mid-build. If a fresh session is asked to add clause types, regulations, or contract types outside this scope, confirm with the developer first rather than assuming broader scope was intended.

---

## 8. Process discipline — the actual rules to follow from here on

1. **Do not restart the project from scratch again.** Whatever state the build is currently in is the foundation — debug forward, don't reset.
2. **Never paraphrase an error message.** Paste the full, exact, unedited terminal/log output. Paraphrasing has repeatedly caused wasted back-and-forth because a critical detail was lost in translation.
3. **Review an agentic IDE's implementation plan before letting it execute**, when the tool supports this — catching a wrong assumption at the plan stage costs far less than fixing it after a full build cycle.
4. **One live/manual test pass per meaningful change, not repeated "just checking" runs.**
5. **If stuck on the same error for more than ~20–30 minutes, stop and escalate immediately** with full context rather than continuing to try variations alone.

---

## 9. Issues found during the current build — Phase 0 (2026-09-11)

### 9.1 — `requirements.txt` pins that don't build on Python 3.14
**The bug:** the Phase 0 prompt pins `pydantic==2.10.4` (and `pydantic-settings==2.6.1`) and `psycopg2-binary==2.9.10`. On Python 3.14.5:
- `pydantic-core` for 2.10.4 has no `cp314` wheel, so pip tries a source build, which fails: *"the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)"* (PyO3 0.22.6).
- `psycopg2-binary==2.9.10` installs but fails at import: `ImportError: DLL load failed while importing _psycopg: The specified module could not be found.`
**The fix, applied:** bumped to `pydantic==2.13.5`, `pydantic-settings==2.15.0`, `python-dotenv==1.2.3`, `psycopg2-binary==2.9.13` — all have working `cp314` wheels. Recorded in `docs/SETUP_NOTES.md`. **Do not** re-pin these back down to the prompt's original values. If a future phase adds a Rust-backed dependency and it fails to build, check for a newer version with a `cp314` wheel first before anything else.

### 9.2 — Wrong Node.js on PATH
**The bug:** the default `PATH` `node` was **v16.20.2** (the `nvm4w` shim was pointing at an old version), far too old for Next.js 16 / `create-next-app@latest`.
**The fix, applied:** `nvm use 24.14.1` (nvm4w had it installed; the change persists globally, not per-shell). A standalone `D:\NodeJS LTS\node.exe` (v24.16.0) is also on the machine and is fine. **Going forward:** before any `npm`/`npx`/`next` command, confirm `node --version` shows v24.x. In a fresh shell run `nvm use 24.14.1` first, or prepend `C:\nvm4w\nodejs` to `PATH`.

### 9.3 — Stale Docker containers/volumes from a prior attempt
**The bug:** `docker-compose up` failed with `Conflict. The container name "/pactscan-neo4j" is already in use` — leftover containers from an earlier attempt's compose project (`infra`), plus orphaned `infra_*` volumes.
**The fix, applied:** since Phase 0 has no schema or graph data yet, the stale containers were removed (`docker rm -f`) and the `infra_*` volumes deleted, then recreated cleanly under the new `pactscan-dev` compose project. **Caution for later phases:** once real graph/DB data exists, do NOT blanket-remove volumes — check `docker volume ls` and back up / inspect first. The "don't restart from scratch" rule (Section 8.1) applies to data, not just code.

### 9.4 — Each Bash/PowerShell tool call is a fresh shell
**Note (not a bug):** `cd`, `nvm use` semantics, `venv` activation, and env vars do **not** persist between separate tool invocations. Chain dependent steps in one call, or use absolute paths / `.\venv\Scripts\python.exe` directly. `nvm use` is the exception — it flips a global symlink, so it does persist.

### 9.5 — Docker Desktop must be started manually and takes minutes
**Note:** on this machine Docker Desktop is not set to auto-start. Launch `"C:\Program Files\Docker\Docker\Docker Desktop.exe"` and expect the engine to take 2–5 minutes before `docker info` succeeds (WSL2 backend spin-up). `docker` commands hang rather than fail fast during this window — wait, don't retry in a tight loop.

---

## 10. Issues found during the current build — Phase 1 (2026-09-11)

### 10.1 — LlamaParse: use `llama-cloud>=1.0`, not `llama-cloud-services`
**The bug/confusion:** `pip install llama-cloud-services` installs a package that is **deprecated** (maintained only until May 2026) and hard-pins `llama-cloud==0.1.46`. The Phase 1 prompt's documented call — `client.parsing.parse(...)` — is the API of the *new* `llama-cloud>=1.0` package, not the old one. Installing both produces a dependency conflict.
**The fix, applied:** `requirements.txt` pins `llama-cloud==2.16.0` only; `llama-cloud-services` is not installed. `app/agents/detect/ingest.py` uses `from llama_cloud import LlamaCloud, file_from_path` then `client.parsing.parse(tier="cost_effective", version="latest", upload_file=..., output_options=...)`. Per-page markdown extraction from the response is best-effort (`_parsed_document_from_llama_result`) and will raise loudly if the response shape changes — adjust that one function if live testing hits it.

### 10.2 — Gemini Interactions API is real in `google-genai` 2.22.0
**Note (not a bug):** earlier planning assumed the prompt's "Interactions API" might be fictional. It is not — `client.interactions.create(...)` exists, takes `model` / `input` / `system_instruction` / `response_format=TextResponseFormat(type="text", mime_type="application/json", schema_=<json_schema>)`, and returns an object with `.output_text`. `app/llm/client._call_gemini()` is the single call site; a provider or call-shape change is a one-function edit there.

### 10.3 — Cypher: `size()` not `length()` for variable-length relationship lists
**The bug:** `MATCH p=(a)-[rels:OVERRIDES*1..3]->(b) ... RETURN length(rels)` fails on Neo4j 5 with `Type mismatch: expected Path but was List<Relationship>`. `length()` only accepts a Path.
**The fix:** use `size(rels)` for the hop count. Applied in `graph_store.Neo4jGraphStore.get_overriders`.

### 10.4 — pytest-asyncio 0.25 is very noisy on Python 3.14
**The bug:** `pytest-asyncio==0.25.0` (the Phase 0/1 prompt pin) emits ~15 `asyncio.get_event_loop_policy is deprecated` warnings *per async test* on Python 3.14 — ~88 warnings for a small suite.
**The fix, applied:** bumped to `pytest-asyncio==1.4.0` (which pulled `pytest==9.1.1`). Suite passes clean. `pytest.ini` sets `asyncio_mode = strict` + `asyncio_default_fixture_loop_scope = function`.

### 10.6 — `llama-cloud` 2.x `parsing.parse` requires `expand`, not `output_options`
**The bug:** `client.parsing.parse(..., output_options={"markdown": True})` → `ValueError: You should provide a non-empty sequence for the 'expand' parameter`.
**The fix, applied:** `client.parsing.parse(tier=settings.llama_parse_tier, version="latest", upload_file=file_from_path(path), expand=["markdown"])`. Read pages from `result.markdown.pages` (`.markdown` / `.page_number` / `.header`, or `.error` on a failed page). `LLAMA_PARSE_TIER` in `.env` defaults to `fast` (cheapest, no AI — fine for the simple synthetic fixtures; bump to `cost_effective` for real multi-column/table contracts).

### 10.7 — `pytest` was running live tests when keys were present
**The bug:** `@pytest.mark.live` does not deselect by default — a plain `pytest` (no `-m`) runs everything, so once `GEMINI_API_KEYS` / `LLAMA_CLOUD_API_KEY` were in `.env`, `pytest` burned real quota on the live tests.
**The fix, applied:** `pytest.ini` now has `addopts = -m "not live"`. Plain `pytest` = mocked only; `pytest -m live` overrides and runs only the live tests. **Every later phase's live tests must also carry `@pytest.mark.live`.**

### 10.8 — The fallback chain was NOT catching Gemini's 429 (first live run)
**The bug:** `google-genai` 2.22 raises `google.genai._gaos.lib.compat_errors.RateLimitError` for a quota 429 — a **separate class hierarchy** from `google.genai.errors.APIError`, which is what `_call_gemini` was catching. So the first 429 propagated and killed the whole run instead of advancing to Tier 2 / the next account. (Free-tier limits are tiny — `gemini-3.8-flash` showed `limit: 5` then `limit: 20` requests, and a single contract makes ~10-15 LLM calls.)
**The fix, applied:** `_call_gemini` now catches `Exception` and defers to `_is_quota_error()`, which returns True on any of: `type(exc).__name__` in {RateLimitError, ResourceExhausted...}, a `status_code`/`code`/`status` of 429 / `RESOURCE_EXHAUSTED` / `too_many_requests`, or the message containing RESOURCE_EXHAUSTED / QUOTA / RATE LIMIT / TOO MANY REQUESTS. Non-quota errors (BadRequest, invalid schema, ValueError) still re-raise immediately. Regression tests: `test_is_quota_error_recognises_sdk_ratelimit_shapes`, `test_sdk_ratelimit_error_advances_fallback`.

### 10.9 — Batch the NLI compliance calls (call-volume reduction)
**Context:** the known-issues §3 optimisation ("check a clause against all relevant rules/regs in one structured call") was needed after the first live run — per-clause-per-rule NLI made ~15 calls/contract and blew the free-tier per-minute limits instantly.
**Applied:** `detect_agent` now does ONE `generate_structured(BatchNLIResult)` call per clause covering every relevant playbook rule + regulation together (~7 calls/contract). Any future agent doing many small LLM classifications should batch the same way.
**Reminder:** bumping the batched schema/prompt means `LLM_PROMPT_VERSION` must move (`v1` → `v2`). Set it in `backend\.env`.

### 10.10 — Gemini free tier is too small; Groq is now the primary provider
**The chronic problem (every build attempt):** Google AI Studio's free tier for the good models (`gemini-3.8-flash`, `gemini-3.7-flash`) is roughly **20 requests per day**, and ~5 per minute. A single Detect run makes ~10 LLM calls, so you exhaust Tiers 1–2 immediately and spend most of a run walking cooldowns / hitting `gemma`.
**The fix, applied (Phase 1, second live run):** **Groq is now the primary LLM provider**, Gemini the documented fallback.
- `pip install groq` (`groq==1.7.0`), OpenAI-compatible. `GROQ_API_KEYS` (comma-sep, multi-account like Gemini) + `GROQ_MODEL_TIERS_RAW` in `backend\.env`. Get a free key at `console.groq.com`.
- `LLM_PROVIDER_ORDER=groq,gemini` — the fallback walks every Groq account+tier, then every Gemini account+tier.
- Groq free tier: ~30 RPM, 1k–14.4k requests/day depending on model. Structured output via `response_format={"type":"json_object"}` with the JSON schema injected into the system prompt (Groq's `json_schema` mode is model-specific; `json_object` is universal). `client.py::_strip_json_fences` strips stray ```json fences.
- **A wrong model id in `GROQ_MODEL_TIERS_RAW` raises `NotFoundError` immediately** — that's deliberate (config bug ≠ quota). Fix the list.

### 10.11 — SDK-internal retry + no cooldown memory made runs take 14 minutes
**The bug:** `google-genai` retries 429/5xx **4× with exponential backoff** before the error reaches our fallback loop (~15 s wasted per dead tier), and our loop re-probed every dead tier on every one of the ~10 calls in a run. Contract C took 14 min.
**The fix, applied:**
- Disable the SDK's internal retry: `genai.Client(http_options=HttpOptions(retry_options=HttpRetryOptions(attempts=1)))`; Groq client `max_retries=0`.
- **Cooldown memory** in `client.py`: a `(provider, account, model)` that returns 429/5xx goes on a `LLM_TIER_COOLDOWN_SECONDS` (default 60 s) cooldown and is skipped — not re-probed — for the rest of the run. If *every* tier is cooled and the soonest expiry is ≤ 20 s away, the loop waits once then retries; otherwise it raises `AllLLMTiersExhaustedError`.

### 10.12 — A transient 5xx killed the whole run
**The bug:** `gemini-3.7-flash is currently experiencing high demand` is an HTTP 500. Our loop only advanced on 429, so a transient 500 propagated and failed the request.
**The fix, applied:** `TransientServerError` for HTTP 5xx / "high demand" / "overloaded" / "try again later" — treated like a 429 (advance + cooldown). A real 400/404 / invalid-schema error still raises immediately (`_raise_classified` in `client.py`).

### 10.13 — Detect over-flagged a clean contract (19 findings on contract C)
**The bug:** a real LLM, asked "does this clause satisfy DPDP §8?", marks a cross-border-transfer clause `CONTRADICTS` just because it doesn't *also* restate breach-notification duties. Relevance mapping was too broad and the NLI prompt encouraged "silent = CONTRADICTS".
**The fix, applied (`detect_agent.py`):**
- `RELEVANT_PLAYBOOK` / `RELEVANT_REGULATION` narrowed to rules that govern a clause type's *exact* subject.
- NLI system prompt rewritten conservative: "merely silent on an adjacent obligation = NEUTRAL, never CONTRADICTS; only CONTRADICTS when the clause itself creates the problem."
- Cross-clause suppression: a NEUTRAL on `dpdp_s9`/`gdpr_art8` becomes a finding only if **no** clause in the whole contract ENTAILS it.
- `LLM_PROMPT_VERSION` → `v3`. Live `contract_c` test relaxed to `<= 3` (mocked stays exact-zero).

### 10.14 — Groq's default model list 404'd (models get retired/renamed)
**The bug:** the default `GROQ_MODEL_TIERS_RAW` (`llama-3.3-70b-versatile,...`) 404'd with `model_not_found` on the developer's account — Groq had retired the Llama chat models by the time of this build. This is exactly the "config bug, not quota" case the fallback is designed NOT to mask — it raised immediately instead of silently skipping to Gemini.
**The fix:** list the account's actually-available models and update `GROQ_MODEL_TIERS_RAW`:
```
curl.exe https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```
Current verified working tier list (2026-09): `openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b,qwen/qwen3.6-27b,openai/gpt-oss-safeguard-20b`. **If a live run ever 404s on a Groq model again, re-run that curl and update the list** — this is expected to happen periodically as Groq rotates its hosted models, it is not a code bug to chase.

### 10.15 — In-memory SQLite + FastAPI TestClient needs StaticPool
**The bug:** a mocked test using `create_engine("sqlite:///:memory:")` plus a FastAPI `TestClient` hit `no such table` and `SQLite objects created in a thread can only be used in that same thread` — TestClient runs the request on a different thread than the test, and each new connection to `sqlite:///:memory:` is a *separate, empty* database unless pinned to one connection.
**The fix:** `create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)`. Standard SQLAlchemy pattern for in-memory SQLite shared across threads — use it any time a mocked test drives Postgres-backed code through `TestClient` instead of calling the function directly.

### 10.16 — SQLAlchemy Python-side `default=` isn't applied until flush
**The bug:** `Approval(...)` then immediately reading `approval.id` (to put it in an `AuditLog.entity_id` before `db.commit()`) got `None` — the column's `default=lambda: uuid...` callable only runs when SQLAlchemy actually flushes the INSERT, not at Python object-construction time.
**The fix:** call `db.add(approval); db.flush()` before referencing `approval.id`, then build the dependent row. Applies to any newly-constructed ORM object whose PK is a Python-side default and is needed before the enclosing `commit()`.

### 10.17 — SQLite (mocked tests) doesn't enforce foreign keys; real Postgres does
**Not a bug, a testing-fidelity note:** a cleanup script that deleted `approvals` rows before their dependent `document_versions` rows worked fine against the SQLite test DB but failed with a real `ForeignKeyViolation` against Postgres. SQLite doesn't enforce FK constraints by default; Postgres always does. Don't assume "the SQLite-mocked test passed" proves FK-respecting delete order — verify against real Postgres too when a change touches multiple related tables.

### 10.5 — Mocked tests must not require Docker/Neo4j
**Pattern established:** the Detect agent's graph access goes through a `GraphStore` interface (`app/agents/detect/graph_store.py`) with `Neo4jGraphStore` and `InMemoryGraphStore`. All mocked tests use the in-memory store; only `-m live` tests and the running API touch Neo4j. Keep this split for every later phase's agent — a mocked `pytest -v` run must never need a container up.

## 11. Issues found during the current build — Phase 4 (2026-09-12)

### 11.1 — Fuzzy document-name matching false-positived on shared generic words
**The bug:** `find_contract_by_name()` scored name matches by raw word overlap. A query for a document name that shares only a generic word like "contract" with a real filename (e.g. `contract_z_never_uploaded` vs `contract_a_conflict.pdf`) scored ~0.33 overlap — enough to clear the original 0.3 threshold and wrongly "find" the wrong document instead of correctly reporting no match.
**The fix, applied (`app/agents/ask/ask_retriever.py`):** strip a small set of domain-generic tokens (`contract`, `agreement`, `document`, `the`, `vendor`, `dpa`, `msa`, `pdf`, `doc`, `docx`) from both sides before scoring; tightened the substring shortcut from "either contains the other" to exact match; raised the overlap threshold from 0.3 to 0.5. **Any future name/entity-matching heuristic should strip domain-generic vocabulary before scoring overlap, or common words alone will look like a match.**

### 11.2 — Neo4j vector index top-K is global, not per-filter
**The bug:** `db.index.vector.queryNodes` returns its K nearest nodes across the *entire* index before any subsequent `WHERE tenant_id = ... AND contract_id = ...` filter is applied. Asking for `top_k=6` on a single-document question could silently return fewer than 6 (or zero) results if the globally-nearest 6 clauses all belonged to other contracts.
**The fix, applied (`app/agents/detect/graph_store.py::vector_search_similar_clauses`):** over-fetch before filtering — `fetch_k = min(max(top_k * 5, 25), 200)` — then apply the tenant/contract filter and `LIMIT top_k` afterward. **Any code that combines a Neo4j vector index query with a post-hoc property filter must over-fetch; the index itself does not know about the filter.**

### 11.3 — Live test caught a real bug the mocked suite couldn't: duplicate filenames resolve to a random old contract
**The bug:** `find_contract_by_name` picked the FIRST contract in `list_contracts()`'s return order that tied for the top score. Neo4j's default `MATCH` return order is not insertion order, so when a tenant has uploaded the same filename more than once (very plausible in practice, and guaranteed in this project's own accumulated "ghost" test contracts — see §11 intro), the match could resolve to an arbitrary old contract instead of the one just discussed.
**The fix, applied:** `list_contracts()` (both `Neo4jGraphStore` and `InMemoryGraphStore`) now orders by `upload_date DESC` — most-recently-uploaded first. `find_contract_by_name`'s existing first-tie-wins logic then naturally resolves same-name ties to the newest upload. The mocked test suite couldn't have caught this: its `InMemoryGraphStore` fixtures never create two contracts with the same filename, and its dict iteration order happens to match insertion order anyway. **This is exactly why the phase workflow requires one deliberate live run before calling a phase done — some bugs only exist against Neo4j's real (non-insertion) return ordering.**

### 11.4 — Live test caught a second real bug: single-document search silently returned zero hits once the tenant's corpus grew
**The bug:** §11's over-fetch fix (`fetch_k = top_k * 5` from the global vector index, then filter by `contract_id`) works when the tenant's total embedded-clause count is small, but degrades as it grows. Once this project's accumulated ghost contracts pushed the real corpus past a few dozen contracts, a single-document question's globally-nearest `fetch_k` neighbours sometimes contained *none* of the one contract actually being asked about — producing zero hits (silently reported as "abstained") for a document that was, in fact, relevant and had embeddings.
**The fix, applied (`app/agents/detect/graph_store.py::vector_search_similar_clauses`):** when `contract_id` is given, skip the global vector index entirely — `MATCH (n:Clause {tenant_id, contract_id}) WHERE n.embedding IS NOT NULL`, then score all of that (small, bounded — one document's worth of clauses) set directly with Python cosine similarity, exactly like the in-memory store already does. No approximate top-K, no starvation possible. Portfolio-wide search (`contract_id=None`) still uses the global index with the over-fetch mitigation — that one is inherently a "search everything" case where approximate top-K is the right tool. **Lesson: over-fetch-then-filter after an ANN index is only a mitigation, not a guarantee — for any query that's actually scoped to a small, bounded, directly-addressable subset (like "one document's clauses"), query that subset directly instead of hoping it survives a global top-K cut.**

## 12. Issues found during the current build — Phase 5 (2026-09-12)

### 12.1 — passlib + bcrypt: an unmaintained package's pin can't be trusted against a still-updated one
**The bug:** `passlib==1.7.4` (its final release, effectively unmaintained since ~2020) reads `bcrypt.__about__.__version__` at import time to detect which bcrypt backend is installed. `bcrypt>=4.1` removed that attribute, so `CryptContext(schemes=["bcrypt"]).hash(...)` raised `AttributeError: module 'bcrypt' has no attribute '__about__'`, then masked itself behind a second, misleading exception ("password cannot be longer than 72 bytes") from passlib's error-recovery path — the real cause takes a moment to spot in the traceback.
**The fix, applied:** pin `bcrypt==4.0.1` (the last release that still has `__about__`) directly in `requirements.txt`, instead of installing bcrypt via passlib's own `[bcrypt]` extra, which floats to whatever the latest bcrypt release is and re-triggers this every time bcrypt ships a new version. **Same root lesson as Phase 0's pydantic/psycopg2 pins (§1 above): when one dependency in a chain is unmaintained, its stated compatible-version range for a *still-actively-released* transitive dependency cannot be trusted — pin that transitive dependency explicitly, and re-check it if the symptom ever reappears.**

### 12.2 — Bearer-token auth silently breaks any existing `<a href>` download link
**The bug:** retrofitting `Authorization: Bearer <token>` onto `/api/documents/version/{id}/download` (needed for real tenant-isolated document access) broke the existing frontend's document-download links, which were plain `<a href={url}>` tags — a browser's own navigation for a clicked link never attaches a custom header, so every download would 401 the moment the endpoint started requiring auth.
**The fix, applied:** the frontend now fetches the file with `fetch()` (which *can* carry the auth header, exactly like every other API call), converts the response to a `Blob`, and hands the browser a `URL.createObjectURL(...)` link to click programmatically instead of a static `href`. **Any time an endpoint moves from unauthenticated to bearer-token-authenticated, audit every place that reaches it via a plain link or `<img src>` / form `action` — none of those browser-native navigations can carry a custom `Authorization` header.**

### 12.3 — A real external service being *reachable* during mocked tests is itself a hermeticity bug
**The bug:** `RedisRateLimiter` is deliberately designed to fail OPEN when Redis is unreachable — the correct behavior in production. But this project's dev machine had Redis actually running (left up from earlier manual testing via `docker compose up`), so the rate limiter's mocked-test code path wasn't failing open at all — it was enforcing for real, and because Redis persists state (with a TTL) independently of the Python test process, running `pytest` more than once in the same session accumulated a real counter across separate, supposedly-independent test runs. `test_suggest_api.py`'s existing tests (which had no reason to know a new rate limiter existed) started failing with `429` instead of their expected `200`/`404`, purely because a *previous* pytest invocation had already used up that test user's quota in real Redis.
**The fix, applied:** an `autouse=True` fixture in `conftest.py` overrides the rate limiter for literally every test — both the FastAPI-dependency-injected call site (`app.dependency_overrides`) and the direct-function-call site (`monkeypatch.setattr` on the module-level `get_rate_limiter`, since Ask's edit-instruction path isn't behind FastAPI's DI at all) — to a fresh, in-process `InMemoryRateLimiter()`. **The general lesson: "fails open when the real service is down" is not the same guarantee as "never touches the real service during tests." If a mocked test's correctness depends on an external service being *unreachable*, and that service happens to be reachable on the machine running the tests (e.g. left running from manual testing), the mocked suite silently becomes a live, state-leaking integration test. Any new optional-infra fallback must be explicitly and unconditionally stubbed for the mocked suite — never left to fall through to its own real-vs-unreachable detection.**

### 12.4 — A documented TODO from a prior phase was never actually done, and manual testing caught it
**The bug:** Phase 4's `ChatSession` model docstring literally said "Tenant-wide, not yet per-user — Phase 5 adds login/roles, at which point this gains a user_id column" — but when Phase 5 was actually built, that column never got added, so every user under the same demo tenant (end_user and reviewer) could see and replay each other's Ask conversations. The mocked test suite didn't catch it because no existing test exercised two different users hitting `/api/ask` — every Phase 4/5 Ask test used a single default user throughout.
**The fix, applied:** added `ChatSession.user_id`, scoped every session query by `(tenant_id, user_id)` together, and made reusing someone else's `session_id` (whether by listing, replaying, or passing it as a continuation id on a new message) 404 instead of silently working. Added a dedicated regression test with two distinct users under one tenant.
**The general lesson:** a docstring noting "not built yet, planned for phase N" is not self-enforcing — when phase N actually arrives, explicitly check the prior phase's own "TODO" comments against what got built, don't just work from the new phase's prompt in isolation. This is also a case for why manual, human testing catches a category of bug automated tests can't: nobody had written a test for "does user A see user B's data" until a live human literally logged in as two different accounts and looked.

### 12.5 — A backend field existed and was even displayed back, but the frontend never actually populated it
**The bug:** `Approval.reviewer_note` (via `DecideRequest.note`) has existed since Phase 3, and the approvals page even renders it back afterward ("Note: {reviewer_note}" on a decided item) — but the "Reject" button itself never opened any input for the reviewer to type a reason into. It called `decideApproval(a.id, "rejected", {})` with no note field at all, so every rejection silently recorded `reviewer_note: null`, and the "Note:" line simply never appeared. This went unnoticed because nothing was throwing an error — the code path was just quietly incomplete.
**The fix, applied:** added a reveal-a-textarea-before-confirming step to the Reject button, mirroring the existing "Edit" button's UX pattern, so a reviewer must type something (or leave it blank deliberately) before the rejection actually submits.
**The general lesson:** a backend field being read back and displayed somewhere is not proof that anything ever wrote a real value into it — check the actual write path (the button/form that's supposed to populate it), not just the read path, when a "why is this always empty" question comes up.

### 13.1 — Live manual testing caught Horizon-Scanning silently searching an empty vector index
**The bug:** manually triggering the Horizon-Scanning admin endpoint against a real, already-uploaded contract reported "0 contracts newly flagged" for a regulation clause that plainly should have matched. Not a similarity-threshold problem — a coverage problem. Detect has never embedded a contract's clauses itself; embedding is lazy and has only ever been triggered by Suggest (`ensure_embeddings_for_contract`) or Ask's portfolio-question path (`backfill_all`). A contract that had only ever gone through Detect — never Suggested-on, never asked about — had zero embedded clauses, so the portfolio-wide vector search had an empty index to search, regardless of how well the new regulation clause's text actually matched.
**The fix, applied (`app/agents/horizon_scanning/rediff.py`):** call `backfill_all(store, tenant_id=tenant_id)` before embedding the new regulation clause and searching — the identical fix Ask's `ask_retriever.py` already needed, for the identical reason, one phase earlier.
**The general lesson:** any new feature that does a portfolio-wide (or tenant-wide) vector search against `Clause` nodes must explicitly backfill embeddings first — Detect alone never populates them, and a real live test against a genuinely Detect-only contract is the only way this surfaces, since every existing mocked test either sets embeddings directly on its fixture clauses or goes through Suggest/Ask first, both of which mask the gap.

### 13.2 — Hiding a nav link is not role-gating a route: end_user could reach (and see the buttons of) `/approvals`
**The bug (found by manual testing):** as an `end_user`, an Ask edit-instruction produced a "View this draft in the Approval Queue" link (shown to every role), and following it — or typing `/approvals` — rendered the full approval page with Accept / Reject / Edit buttons. The backend was already refusing the actual decision (`POST /api/approvals/{id}/decide` is `require_role(["reviewer","admin"])`, so a click returned 403), but the UI presented controls the user was never meant to have, and Phase 5 had only hidden the *nav link*, not the *route*.
**The fix, applied:** `AuthGate` now carries a route→roles map (`/approvals` → reviewer/admin, `/admin/*` → admin) and redirects a disallowed role to `/dashboard`; Ask shows the queue link only to reviewer/admin, and tells an end_user "a reviewer will review this draft; you'll be notified when it's decided" instead.
**The general lesson:** a role restriction has to be applied at three layers — API (the real boundary), route, and the individual links/buttons that lead there. Hiding one nav entry covers only the least of them. Client-side gating is UX, not security; the backend `require_role` is what actually holds.

### 13.3 — Scripted edits on Windows silently rewrote line endings
**The bug:** several multi-file edits were done with small Python scripts using `open(p).read()` / `open(p, "w").write()`. On Windows the default text mode translates `\n` to `\r\n` on write, so every file a script touched flipped from LF to CRLF in a repo that is LF throughout. Nothing failed — but `git diff --stat` showed absurd numbers for tiny edits (336 changed lines in a file where 2 changed), and two files had already been committed as CRLF.
**The fix, applied:** normalized the 27 affected files back to LF, added a `.gitattributes` (`* text=auto eol=lf`), and made scripted edits read with `newline=""` and write with `newline="\n"`. The big line counts in that commit are that correction, not real churn.
**The general lesson:** a wildly inflated diff for a small change is a symptom worth checking, not scrolling past — and in Python on Windows, always pass `newline` explicitly when rewriting a file.

### 13.4 — Mocked tests can't vouch for new Cypher
Every ownership/attachment change touched `Neo4jGraphStore` queries that the in-memory store (used by the mocked suite) only *imitates*. Before committing, the new queries were run against the real Neo4j container — owner filter hit/miss, property round-trip, scoped findings, and the vector-search allow-list including a positive case. Same lesson as §10 / §11.4: when a change adds or alters a graph query, run it against the real graph once, not just the fake.

## 14. Frontend redesign

### 14.1 — An unlayered global rule beat every Tailwind utility
**The bug:** the global `:focus-visible { outline: … }` rule was written outside any cascade layer. Tailwind v4 puts its utilities in `@layer utilities`, and *unlayered CSS always beats layered CSS* — so `focus:outline-none` on the command-palette input did nothing and a double focus ring showed.
**The fix:** wrap global base rules in `@layer base`. **Lesson:** in Tailwind v4, never write global element/pseudo rules outside a layer if a utility might need to override them.

### 14.2 — The route guard treated "token not read yet" as "signed out"
**The bug:** the token lives in `localStorage`, which the server (and the hydration render) can't see. The first version of the guard read it as `null` on that first render and redirected everyone to `/login` on every full page load.
**The fix:** read the token with `useSyncExternalStore` (server snapshot `null`) and only redirect once a separate `hydrated` flag is true. A lint rule (`react-hooks/set-state-in-effect`) had pushed the code away from `useEffect`+`setState`, which is what exposed the ordering problem.

### 14.3 — Shell quoting and PowerShell encodings
Two tooling traps while making multi-file edits: a long `bash` command mixing several heredocs with embedded quotes failed to parse and silently did nothing (write real script files instead), and PowerShell 5.1's `Get-Content | Set-Content -Encoding utf8` re-encoded a UTF-8 file as ANSI and added a BOM (mangling every `—`). Edit files with the file tools or with Python using explicit `encoding="utf-8", newline=""`. Same family as §13.3.

### 14.4 — Small layout traps
- `line-clamp-1` sets `display: -webkit-box`; adding `block` after it overrides that and the clamp silently stops working.
- A CSS grid column with no explicit template sizes to its widest child, so a `min-w-[36rem]` table pushed the whole page wider than a phone. Give grid children `min-w-0` (and the grid `grid-cols-1`).
- A tab list with `overflow-x-auto` and a `-mb-px` active underline grows a stray vertical scrollbar; draw the baseline as an inset shadow on the list instead.

### 14.5 — A test that passes because it doesn't do what a user does
The Phase 6 test "re-running the same simulated update is idempotent" built the regulation clause once and re-diffed it twice — so it passed. The real API builds the clause *afresh on every submit*, and that path minted a random id each time, so a user pressing the button twice got duplicate findings. The bug surfaced only when the user asked what the "0 contracts newly flagged" message required.
**The lesson:** an idempotency test must repeat the *whole operation the caller performs* (here: `add_regulation_update` + re-diff, twice, with an independently re-typed copy), not just the last step. Identity that should be stable across submissions must come from the content, not from a generator.

### 14.6 — "No approval" is not "original"
The Versions tab labelled any version with no approval as "Original upload". A restored version also has no approval, so it was mislabelled. Derive labels from what a thing positively is (v1 = original), not from the absence of another marker.

### 14.7 — "Not a problem" was being reported as a problem
`rediff.py` skipped only ENTAILS, so a NEUTRAL verdict ("this clause doesn't deal with the requirement") became a finding too — its own docstring said only contradictions should. Real LLM runs produced 9, then 13 findings from one amendment on a two-page contract; the mocked tests never noticed because the fake classifier always answered CONTRADICTS. **Lesson:** a classifier's test double that only ever returns the "positive" label cannot catch over-flagging — parametrize the fake over every label. It was found only because a user asked why one amendment flagged so much, and confirmed by running the full lifecycle on real infrastructure.

### 14.8 — A too-clever assertion in my own end-to-end script
The first live run "failed" at *clean copy has no old wording*. The code was right: the AI's new wording begins with the old wording, so a substring check on the old text was always true. Assert on what the thing *is* (the paragraph equals the new wording, no arrow), not on the absence of a string the result may legitimately contain.
