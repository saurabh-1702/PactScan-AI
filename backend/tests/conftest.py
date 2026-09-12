"""Shared test fixtures.

* PDF fixtures are generated once per session before any test runs.
* The LLM abstraction and LlamaParse are mocked by default — deterministic,
  zero API cost. ``@pytest.mark.live`` tests opt back into the real services.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.detect.ingest import ParsedDocument, ParsedPage
from app.agents.detect.seed_data import seed
from app.api.deps import CurrentUser
from app.models.clause import (
    BatchNLIItem,
    BatchNLIResult,
    ClauseExtractionResult,
    ClauseType,
    ConfidenceLevel,
    NLILabel,
    OverrideCheckResult,
    _LLMClause,
)
from app.models.redline import (
    ContrarianArgument,
    JudgeVerdict,
    NegotiationFallback,
    ProposedRedline,
)
from app.models.ask import (
    AskAnswer,
    AskScope,
    AskSource,
    DocumentScope,
    GeneralLegalAnswer,
    ScopeClassification,
)
from tests.fixtures.generate_fixtures import (
    CONTRACT_A_PAGES,
    CONTRACT_B_PAGES,
    CONTRACT_C_PAGES,
    generate_all,
)


# --------------------------------------------------------------------------- #
# PDF fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _generate_pdf_fixtures():
    generate_all(force=False)


@pytest.fixture
def fixture_pdf():
    paths = generate_all(force=False)

    def _get(name: str) -> Path:
        return paths[name]

    return _get


# --------------------------------------------------------------------------- #
# Canned parsed documents (keyed by filename)
# --------------------------------------------------------------------------- #
def _doc_from_pages(filename: str, pages: list[list[str]]) -> ParsedDocument:
    parsed_pages = []
    for i, blocks in enumerate(pages, start=1):
        text = "\n\n".join(b[2:] if b.startswith("# ") else b for b in blocks)
        parsed_pages.append(ParsedPage(page_number=i, text=text))
    return ParsedDocument(filename=filename, pages=parsed_pages)


_CANNED_DOCS = {
    "contract_a_conflict.pdf": lambda: _doc_from_pages("contract_a_conflict.pdf", CONTRACT_A_PAGES),
    "contract_b_regulation_gap.pdf": lambda: _doc_from_pages("contract_b_regulation_gap.pdf", CONTRACT_B_PAGES),
    "contract_c_clean.pdf": lambda: _doc_from_pages("contract_c_clean.pdf", CONTRACT_C_PAGES),
}


# --------------------------------------------------------------------------- #
# Fake LLM — routes on prompt / schema content
# --------------------------------------------------------------------------- #
class _FakeLLM:
    """Deterministic stand-in for app.llm.client.generate_structured."""

    async def generate_structured(self, prompt, schema, system_prompt=None):
        name = schema.__name__
        if name == "ClauseExtractionResult":
            return self._extract(prompt)
        if name == "OverrideCheckResult":
            return self._override(prompt)
        if name == "BatchNLIResult":
            return self._batch_nli(prompt)
        if name == "ProposedRedline":
            return ProposedRedline(
                proposed_clause_text=(
                    "Liability for data-breach and confidentiality events shall not be capped "
                    "below the greater of twelve (12) months' fees paid hereunder or the "
                    "negotiated data-incident floor, and any change to this cap must be made by "
                    "a signed written amendment to this Section, not a Statement of Work."
                ),
                rationale=(
                    "Aligns the liability cap with the playbook's required floor and makes any "
                    "future change explicit and conspicuous rather than buried in an SOW addendum."
                ),
                confidence=80,
            )
        if name == "ContrarianArgument":
            return ContrarianArgument(
                argument=(
                    "The SOW addendum expressly cross-references MSA Section 8.2(a) and was "
                    "signed by both parties, so the counterparty had clear notice of the change."
                ),
                strongest_point="Explicit cross-reference puts the counterparty on notice.",
                confidence=40,
            )
        if name == "JudgeVerdict":
            return JudgeVerdict(
                verdict="downgraded",
                final_confidence=60,
                reasoning=(
                    "The cross-reference mitigates the notice concern somewhat, but the cap "
                    "change still was not made as a conspicuous MSA amendment, so a residual "
                    "concern remains."
                ),
            )
        if name == "NegotiationFallback":
            return NegotiationFallback(
                predicted_pushback="The vendor will resist re-opening the MSA for a formal amendment.",
                fallback_clause_text=(
                    "Alternative: incorporate the SOW's liability cap by reference directly into "
                    "MSA Section 8.2(a) via a short, separately-signed addendum."
                ),
            )
        if name == "ScopeClassification":
            return self._classify_scope(prompt)
        if name == "AskAnswer":
            return self._ask_answer(prompt)
        if name == "GeneralLegalAnswer":
            return GeneralLegalAnswer(
                answer_text=(
                    "This is general legal-tech information, not specific to your contracts, and "
                    "not a substitute for advice from a qualified lawyer."
                )
            )
        raise AssertionError(f"_FakeLLM has no route for schema {name}")

    # -- Ask agent routing (Phase 4) ---------------------------------
    _FIXTURE_NAMES = (
        "contract_a_conflict",
        "contract_b_regulation_gap",
        "contract_c_clean",
    )

    def _extract_user_message(self, prompt: str) -> str:
        return _section(prompt, "USER MESSAGE:\n", "\n\nClassify it.")

    def _mentioned_fixture(self, lower_text: str) -> str | None:
        """Recognizes any 'contract_xxx'-shaped token as a named-document
        reference, whether or not it's one of the real fixtures — so an
        unmatched name (e.g. 'contract_z_never_uploaded') still routes through
        the single-document path and correctly fails to fuzzy-match later,
        rather than silently falling back to a portfolio-wide search."""
        m = re.search(r"contract_[a-z0-9_]+", lower_text)
        if m:
            return m.group(0)
        for name in self._FIXTURE_NAMES:
            if name.replace("_", " ") in lower_text:
                return name
        return None

    def _classify_scope(self, prompt: str) -> ScopeClassification:
        message = self._extract_user_message(prompt)
        lower = message.lower()

        if any(w in lower for w in ("weather", "capital of france", "recipe", "football score")):
            return ScopeClassification(scope=AskScope.OUT_OF_SCOPE)

        if lower.strip().startswith("edit "):
            rest = message[len("edit "):]
            if " to " in rest:
                doc_part, change_part = rest.split(" to ", 1)
            elif ":" in rest:
                doc_part, change_part = rest.split(":", 1)
            else:
                doc_part, change_part = rest, "Apply the requested change."
            return ScopeClassification(
                scope=AskScope.EDIT_INSTRUCTION,
                document_scope=DocumentScope.SINGLE,
                mentioned_document_name=doc_part.strip(),
                requested_change=change_part.strip(),
            )

        if "what is the dpdp act" in lower or "typical liability cap" in lower or "legal tech" in lower:
            return ScopeClassification(scope=AskScope.GENERAL_LEGAL_TECH_QUESTION)

        status_markers = (
            "what issues", "what was suggested", "what has been fixed", "findings",
            "were detected", "been approved", "compliance status", "what's pending",
        )
        if any(m in lower for m in status_markers):
            doc_name = self._mentioned_fixture(lower)
            time_ref = None
            for phrase in ("last week", "this week", "last month", "this month", "today", "yesterday"):
                if phrase in lower:
                    time_ref = phrase
            return ScopeClassification(
                scope=AskScope.COMPLIANCE_STATUS_QUESTION,
                document_scope=DocumentScope.SINGLE if doc_name else DocumentScope.PORTFOLIO,
                mentioned_document_name=doc_name,
                time_reference=time_ref,
            )

        doc_name = self._mentioned_fixture(lower)
        return ScopeClassification(
            scope=AskScope.CONTRACT_QUESTION,
            document_scope=DocumentScope.SINGLE if doc_name else DocumentScope.PORTFOLIO,
            mentioned_document_name=doc_name,
        )

    def _ask_answer(self, prompt: str) -> AskAnswer:
        # echoes back whichever [document_name, page N] / [document_name] markers
        # actually appear in the retrieved-context block passed into the prompt —
        # a deterministic proxy for "the answer cites what was actually retrieved"
        matches = re.findall(r"\[([^,\]]+)(?:,\s*page\s*(\d+))?\]", prompt)
        seen: set[tuple[str, int]] = set()
        sources: list[AskSource] = []
        for name, page in matches:
            name = name.strip()
            page_number = int(page) if page else 0
            key = (name, page_number)
            if key in seen:
                continue
            seen.add(key)
            sources.append(AskSource(document_name=name, page_number=page_number))
        if not sources:
            return AskAnswer(answer_text="I don't have information about that in your contract portfolio.", sources=[])
        return AskAnswer(answer_text="Here is what the portfolio shows, with citations.", sources=sources)

    async def generate_text(self, prompt, system_prompt=None):
        raise AssertionError("generate_text not expected in this suite")

    # -- clause extraction --------------------------------------------
    def _extract(self, prompt: str) -> ClauseExtractionResult:
        if "80,00,000" in prompt or "Four Crore" in prompt:
            return ClauseExtractionResult(
                clauses=[
                    _LLMClause(
                        clause_type=ClauseType.LIMITATION_OF_LIABILITY,
                        page_number=1,
                        section_header="Section 8. Limitation of Liability",
                        raw_text="8.2 (a) the total aggregate liability of either party shall not exceed Rupees 80,00,000 (Rupees Eighty Lakh only).",
                        confidence=ConfidenceLevel.high,
                    ),
                    _LLMClause(
                        clause_type=ClauseType.GOVERNING_LAW,
                        page_number=1,
                        section_header="Section 12. Governing Law",
                        raw_text="This Agreement shall be governed by the laws of India, and the courts at Bengaluru shall have exclusive jurisdiction.",
                        confidence=ConfidenceLevel.high,
                    ),
                    _LLMClause(
                        clause_type=ClauseType.LIMITATION_OF_LIABILITY,
                        page_number=2,
                        section_header="4. Data-Breach Liability",
                        raw_text="4.1 Notwithstanding Section 8.2(a) of the MSA, liability for data-breach events under this SOW shall not exceed Rupees 4,00,00,000 (Rupees Four Crore only). This provision supersedes the general liability cap in the MSA in respect of data-breach events only.",
                        confidence=ConfidenceLevel.high,
                    ),
                ]
            )
        if "appropriate consents" in prompt:
            return ClauseExtractionResult(
                clauses=[
                    _LLMClause(
                        clause_type=ClauseType.DATA_PROCESSING,
                        page_number=1,
                        section_header="2. Purpose and Scope",
                        raw_text="2.1 The Processor shall process personal data solely to provide the hosting, storage and analytics services described in the applicable order form.",
                        confidence=ConfidenceLevel.high,
                    ),
                    _LLMClause(
                        clause_type=ClauseType.DATA_PROCESSING,
                        page_number=1,
                        section_header="3. Consent",
                        raw_text="3.1 The Vendor shall obtain appropriate consents for the processing of personal data as required under applicable law.",
                        confidence=ConfidenceLevel.medium,
                    ),
                    _LLMClause(
                        clause_type=ClauseType.BREACH_NOTIFICATION,
                        page_number=2,
                        section_header="6. Security and Breach Notification",
                        raw_text="6.1 The Processor shall notify the Fiduciary of any personal-data breach without undue delay and in any event within 72 hours of becoming aware of it.",
                        confidence=ConfidenceLevel.high,
                    ),
                    _LLMClause(
                        clause_type=ClauseType.SUBPROCESSOR_OBLIGATIONS,
                        page_number=2,
                        section_header="7. Sub-processing",
                        raw_text="7.1 The Processor shall not engage any sub-processor without the prior written authorisation of the Fiduciary.",
                        confidence=ConfidenceLevel.high,
                    ),
                    _LLMClause(
                        clause_type=ClauseType.TERMINATION,
                        page_number=2,
                        section_header="8. Data Deletion",
                        raw_text="8.1 On termination the Processor shall delete or return all personal data within 30 days and certify such deletion in writing.",
                        confidence=ConfidenceLevel.high,
                    ),
                ]
            )
        # clean contract
        return ClauseExtractionResult(
            clauses=[
                _LLMClause(
                    clause_type=ClauseType.GOVERNING_LAW, page_number=1,
                    section_header="1. Governing Law",
                    raw_text="1.1 This DPA is governed by the laws of India, including the DPDP Act, 2023.",
                    confidence=ConfidenceLevel.high,
                ),
                _LLMClause(
                    clause_type=ClauseType.DATA_PROCESSING, page_number=1,
                    section_header="2. Purpose, Data Categories and Retention",
                    raw_text="2.1 The Processor processes contact details and service-usage records of the Fiduciary's adult enterprise users solely to deliver the contracted services. 2.2 Personal data is retained for the term plus 90 days, then deleted. The Services are not directed to children and the Processor shall not knowingly process personal data of anyone under 18.",
                    confidence=ConfidenceLevel.high,
                ),
                _LLMClause(
                    clause_type=ClauseType.LIMITATION_OF_LIABILITY, page_number=2,
                    section_header="4. Limitation of Liability",
                    raw_text="4.1 Liability of the Processor for data-breach and confidentiality events shall not exceed the greater of twelve months' fees or Rupees 5,00,00,000. Any change to this cap must be a signed written amendment expressly referencing this Section 4.1.",
                    confidence=ConfidenceLevel.high,
                ),
                _LLMClause(
                    clause_type=ClauseType.BREACH_NOTIFICATION, page_number=2,
                    section_header="5. Breach Notification",
                    raw_text="5.1 The Processor shall notify the Fiduciary and the Data Protection Board of India of any personal-data breach within 72 hours of becoming aware of it.",
                    confidence=ConfidenceLevel.high,
                ),
                _LLMClause(
                    clause_type=ClauseType.DATA_LOCALIZATION_CROSS_BORDER_TRANSFER, page_number=2,
                    section_header="6. Cross-Border Transfer and Localisation",
                    raw_text="6.1 Personal data is stored and processed within India, and transferred outside India only to jurisdictions not restricted by the Central Government subject to appropriate safeguards.",
                    confidence=ConfidenceLevel.high,
                ),
                _LLMClause(
                    clause_type=ClauseType.AUDIT_RIGHTS, page_number=2,
                    section_header="7. Audit Rights",
                    raw_text="7.1 The Fiduciary may audit the Processor's data-processing practices, directly or via an independent auditor, once per year and after any breach.",
                    confidence=ConfidenceLevel.high,
                ),
                _LLMClause(
                    clause_type=ClauseType.SUBPROCESSOR_OBLIGATIONS, page_number=2,
                    section_header="8. Sub-processors",
                    raw_text="8.1 The Processor shall obtain the Fiduciary's prior written approval before engaging a sub-processor and shall flow down equivalent obligations.",
                    confidence=ConfidenceLevel.high,
                ),
            ]
        )

    # -- override confirmation --------------------------------------
    def _override(self, prompt: str) -> OverrideCheckResult:
        has_notwithstanding = "notwithstanding" in prompt.lower()
        both_caps = "4,00,00,000" in prompt and "80,00,000" in prompt
        if has_notwithstanding and both_caps:
            return OverrideCheckResult(
                overrides=True,
                scope="data-breach events",
                reasoning="Clause A expressly supersedes the MSA liability cap for data-breach events.",
            )
        return OverrideCheckResult(overrides=False, scope="", reasoning="No change of legal effect.")

    # -- batched NLI classification --------------------------------
    def _batch_nli(self, prompt: str) -> BatchNLIResult:
        clause = _section(prompt, "CLAUSE (effective text):", "REQUIREMENTS:")
        req_block = _section(prompt, "REQUIREMENTS:", "Classify the clause")

        vague_consent_clause = "appropriate consents" in clause
        addresses_children = (
            "not directed to children" in clause
            or "under 18" in clause
            or "under 18 years" in clause
            or "parental" in clause.lower()
        )
        liability_msa = "80,00,000" in clause
        liability_compliant = "twelve months' fees" in clause or "5,00,00,000" in clause

        results: list[BatchNLIItem] = []
        for line in req_block.splitlines():
            line = line.strip()
            m = re.search(r"requirement_id=['\"]?([\w.]+)['\"]?\s*:\s*(.*)", line)
            if not m:
                continue
            req_id, req_text = m.group(1), m.group(2)
            is_child_consent_req = (
                "verifiable consent of a parent" in req_text
                or "child's personal data" in req_text
                or "parental responsibility" in req_text
                or "child" in req_text.lower()
            ) or req_id in {"dpdp_s9", "gdpr_art8", "pb_verifiable_parental_consent"}

            if is_child_consent_req and addresses_children:
                results.append(
                    BatchNLIItem(
                        requirement_id=req_id,
                        label=NLILabel.ENTAILS,
                        explanation="The clause expressly excludes processing children's data.",
                        confidence=ConfidenceLevel.high,
                    )
                )
            elif is_child_consent_req and vague_consent_clause:
                results.append(
                    BatchNLIItem(
                        requirement_id=req_id,
                        label=NLILabel.CONTRADICTS
                        if req_id in {"dpdp_s9", "gdpr_art8"}
                        else NLILabel.NEUTRAL,
                        explanation=(
                            "The clause only requires 'appropriate consents' generally and is "
                            "silent on children's data and verifiable parental consent."
                        ),
                        confidence=ConfidenceLevel.high
                        if req_id in {"dpdp_s9", "gdpr_art8"}
                        else ConfidenceLevel.low,
                    )
                )
            elif is_child_consent_req:
                results.append(
                    BatchNLIItem(
                        requirement_id=req_id,
                        label=NLILabel.NEUTRAL,
                        explanation="Clause does not address children's data.",
                        confidence=ConfidenceLevel.low,
                    )
                )
            elif liability_msa:
                results.append(
                    BatchNLIItem(
                        requirement_id=req_id,
                        label=NLILabel.NEUTRAL,
                        explanation="Liability cap covered by the dedicated override check.",
                        confidence=ConfidenceLevel.low,
                    )
                )
            elif liability_compliant:
                results.append(
                    BatchNLIItem(
                        requirement_id=req_id,
                        label=NLILabel.ENTAILS,
                        explanation="Amendment control makes any cap change explicit.",
                        confidence=ConfidenceLevel.high,
                    )
                )
            else:
                results.append(
                    BatchNLIItem(
                        requirement_id=req_id,
                        label=NLILabel.ENTAILS,
                        explanation="The clause satisfies the requirement.",
                        confidence=ConfidenceLevel.high,
                    )
                )
        return BatchNLIResult(results=results)


def _section(text: str, start: str, end: str) -> str:
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.DOTALL)
    return m.group(1).strip() if m else ""


# --------------------------------------------------------------------------- #
# Fixtures wiring the fakes in
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_llm(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr("app.llm.client.generate_structured", fake.generate_structured)
    monkeypatch.setattr("app.llm.client.generate_text", fake.generate_text)
    return fake


def _fake_embedding_vector(text: str) -> list[float]:
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:16]]


@pytest.fixture
def fake_embed(monkeypatch):
    async def _embed(text: str) -> list[float]:
        return _fake_embedding_vector(text)

    monkeypatch.setattr("app.llm.client.generate_embedding", _embed)
    return _embed


@pytest.fixture
def db_session():
    """An in-memory SQLite session for redline_suggestions — no Docker/Postgres
    needed for the mocked suite."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.db.models  # noqa: F401 - registers RedlineSuggestion on Base
    from app.db.postgres_client import Base

    # StaticPool + check_same_thread=False: a single shared in-memory SQLite
    # connection, since FastAPI's TestClient runs requests on another thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_parse(monkeypatch):
    def _parse(file_path):
        name = Path(file_path).name
        if name in _CANNED_DOCS:
            return _CANNED_DOCS[name]()
        raise AssertionError(f"No canned parse for {name}")

    monkeypatch.setattr("app.agents.detect.ingest.parse_document", _parse)
    return _parse


# --------------------------------------------------------------------------- #
# Auth (Phase 5) — API tests that exercise endpoint wiring rather than
# auth/role-gating itself all default to this admin user under DEMO_TENANT,
# matching the tenant_id the rest of these fixtures build data under.
# test_auth_and_dashboard.py overrides get_current_user explicitly per-test
# instead, to actually exercise 401/403 paths.
# --------------------------------------------------------------------------- #
def default_current_user() -> CurrentUser:
    return CurrentUser(user_id="usr_test_admin", tenant_id=DEMO_TENANT, role="admin")


@pytest.fixture
def store():
    return InMemoryGraphStore()


@pytest.fixture
def seeded_store(store):
    seed(store)
    return store
