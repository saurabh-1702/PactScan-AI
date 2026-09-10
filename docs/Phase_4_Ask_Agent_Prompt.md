# PHASE 4 — Ask Agent (Portfolio-Wide Conversational Q&A) — Windows Edition
### Prompt for Claude Code (paste this entire file as your instruction)

---

## PROJECT CONTEXT (read this first)

You are building **PactScan AI**, an agentic GraphRAG platform for legal contract compliance, scoped to SaaS/vendor Data Processing Agreements under India's DPDP Act (primary regulation; GDPR secondary). This is **Phase 4** of a 7-phase build. By now you have: Phase 1's Detect Agent, Phase 2's Suggest Agent (with a Retriever doing hybrid vector + Cypher search, and the provider-agnostic `app\llm\client.py` abstraction backed by a caching + 7-tier model + multi-account fallback LLM abstraction (Google Gemini, 3 accounts, extensible)), Phase 3's Fix & Learn (approval-gated document writing, with `document_versions` tracking). Assume all of this exists and works. The real `.env` lives only at `backend\.env`.

**What Phase 4 must prove:** a user can ask free-form natural-language questions about their entire contract portfolio (not just one document) and get grounded, cited answers — reusing Phase 2's Retriever and the shared `app\llm\client.py` abstraction rather than building new infrastructure. The agent must explicitly say "I don't know" when nothing in the graph supports an answer, rather than guessing. Optionally (stretch goal), a user can also issue a conversational edit instruction that hands off to Phase 2's Suggest pipeline — but this must still land in Phase 3's approval queue, never bypassing it.

**Do NOT build in this phase:** login/roles (Phase 5), horizon-scanning (Phase 6). Continue using the hardcoded `tenant_id = "demo_tenant"` from Phase 1.

---

## WINDOWS NOTE
Continue using `venv\Scripts\Activate.ps1` and `curl.exe` for manual testing.

---

## STEP-BY-STEP BUILD INSTRUCTIONS

### 1. Build the scope-classifier (`backend\app\agents\ask\scope_classifier.py`)
A `generate_structured()` call (from `app\llm\client.py`) that takes the user's message and classifies it into exactly one of:
- `PORTFOLIO_QUESTION` — asks about multiple/unspecified contracts (e.g., "which of our contracts have X")
- `SINGLE_DOCUMENT_QUESTION` — names a specific contract (e.g., "summarize the NovaHealth vendor DPA")
- `EDIT_INSTRUCTION` — asks for a change to be made (e.g., "edit the NovaHealth vendor DPA to change X")
- `OUT_OF_SCOPE` — anything unrelated to contracts/compliance

### 2. Build the retrieval wrapper (`backend\app\agents\ask\ask_retriever.py`)
- For `PORTFOLIO_QUESTION`: call Phase 2's Retriever without restricting to a single `contract_id` — search across all contracts under `tenant_id = "demo_tenant"`.
- For `SINGLE_DOCUMENT_QUESTION`: first resolve the named document to a `contract_id` (fuzzy match against stored filenames/contract names in the graph — if no match is found, return a clear "I don't have a document by that name" response), then call the Retriever scoped to just that `contract_id`.
- For both: if the Retriever returns no relevant results above a reasonable similarity threshold, do not call the LLM to "make something up" — return an explicit abstention response: `"I don't have information about that in your contract portfolio."`

### 3. Build the answer-generation call (`backend\app\agents\ask\answer_generator.py`)
- Call `generate_structured()` (from `app\llm\client.py`) with the user's question and the retrieved context (clause text + source document name + page number for each retrieved item).
- **Require the model to cite the source document name and page for every factual claim in its answer** — instruct this explicitly in the system prompt, and if multiple documents are cited, require the answer to clearly attribute which claim came from which document.
- Return the answer as structured output: an `answer_text` field plus a `sources` list of `{document_name, page_number}`.

### 4. (STRETCH GOAL) Edit-instruction handoff (`backend\app\agents\ask\edit_handoff.py`)
- If the scope-classifier returns `EDIT_INSTRUCTION`, resolve the named document + described change into the same input shape Phase 2's `POST /api/suggest/standalone` expects, and call it internally.
- The response to the user must make clear that this produced a **draft awaiting approval**, not a completed edit.
- Do not add any new write path here — this function must only ever call Phase 2's Suggest endpoint, never Phase 3's Executor directly.

### 5. Build the FastAPI endpoint (`backend\app\api\ask.py`)
- `POST /api/ask` — accepts `{"message": string, "session_id": string}`, runs scope-classifier → retrieval → answer generation (→ edit handoff if applicable), returns the answer + sources + a `type` field indicating which path was taken.

### 6. Frontend — build a chat UI (`frontend\app\ask\page.tsx`)
- A message list + text input, styled minimally.
- Render each assistant response with its citations shown distinctly.
- If an edit-instruction response comes back, show a distinct visual indicator linking to Phase 3's approval queue page.

---

## TESTS TO WRITE (`backend\tests\test_ask_agent.py`)
- Test a `SINGLE_DOCUMENT_QUESTION` naming one of the Phase 1 sample contracts by name — assert the response cites that specific document.
- Test a `PORTFOLIO_QUESTION` (e.g., "which contracts mention liability caps") — assert the response draws from more than one of the sample contracts, with each claim attributed to the correct source document.
- Test an out-of-scope question — assert correct routing to `OUT_OF_SCOPE` with no attempt to answer as if it were contract-related.
- Test a question about a document that was never uploaded — assert an explicit "I don't have that document" response rather than a fabricated answer.
- If edit-instruction handoff was built: test that it results in a new row in `redline_suggestions` and `approvals` (status `pending`), with no file on disk changed.

## EXIT CRITERIA FOR THIS PHASE
All tests above pass. You can open the chat UI, ask a portfolio-wide question, a single-document question, and an intentionally unanswerable question, and get correctly differentiated, correctly cited (or correctly abstained) responses each time. Do not proceed to Phase 5 until the abstention behavior is proven to work via an actual passing test.
