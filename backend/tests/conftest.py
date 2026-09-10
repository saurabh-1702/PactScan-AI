"""Shared test fixtures.

* PDF fixtures are generated once per session before any test runs.
* The LLM abstraction and LlamaParse are mocked by default — deterministic,
  zero API cost. ``@pytest.mark.live`` tests opt back into the real services.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.ingest import ParsedDocument, ParsedPage
from app.agents.detect.seed_data import seed
from app.models.clause import (
    ClauseExtractionResult,
    ClauseType,
    ConfidenceLevel,
    NLILabel,
    NLIResult,
    OverrideCheckResult,
    _LLMClause,
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
        if name == "NLIResult":
            return self._nli(prompt)
        raise AssertionError(f"_FakeLLM has no route for schema {name}")

    async def generate_text(self, prompt, system_prompt=None):
        raise AssertionError("generate_text not expected in Phase 1")

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

    # -- NLI classification -----------------------------------------
    def _nli(self, prompt: str) -> NLIResult:
        clause = _section(prompt, "CLAUSE (effective text):", "REQUIREMENT:")
        requirement = _section(prompt, "REQUIREMENT:", "Classify the clause")

        is_child_consent_req = (
            "verifiable consent of a parent" in requirement
            or "child's personal data" in requirement
            or "parental responsibility" in requirement
            or "child's consent" in requirement.lower()
        )
        vague_consent_clause = "appropriate consents" in clause

        if is_child_consent_req and vague_consent_clause:
            return NLIResult(
                label=NLILabel.CONTRADICTS,
                explanation=(
                    "The clause only requires 'appropriate consents' generally and is silent on "
                    "children's data and verifiable parental consent, so the agreement would "
                    "permit non-compliant processing of a child's personal data."
                ),
                confidence=ConfidenceLevel.high,
            )
        if is_child_consent_req:
            # other clauses don't address children — genuine but low-signal gap
            return NLIResult(
                label=NLILabel.NEUTRAL,
                explanation="Clause does not address children's data.",
                confidence=ConfidenceLevel.low,
            )
        # liability override case: leave NLI neutral, the override finding covers it
        if "80,00,000" in clause or "twelve months' fees" in clause or "5,00,00,000" in clause:
            return NLIResult(
                label=NLILabel.NEUTRAL if "80,00,000" in clause else NLILabel.ENTAILS,
                explanation="Liability cap handled by dedicated override check / compliant amendment control.",
                confidence=ConfidenceLevel.low,
            )
        # everything else in the clean / compliant contracts satisfies its rule
        return NLIResult(
            label=NLILabel.ENTAILS,
            explanation="The clause satisfies the requirement.",
            confidence=ConfidenceLevel.high,
        )


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


@pytest.fixture
def fake_parse(monkeypatch):
    def _parse(file_path):
        name = Path(file_path).name
        if name in _CANNED_DOCS:
            return _CANNED_DOCS[name]()
        raise AssertionError(f"No canned parse for {name}")

    monkeypatch.setattr("app.agents.detect.ingest.parse_document", _parse)
    return _parse


@pytest.fixture
def store():
    return InMemoryGraphStore()


@pytest.fixture
def seeded_store(store):
    seed(store)
    return store
