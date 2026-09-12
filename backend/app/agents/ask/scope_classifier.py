"""Ask agent — scope classification.

One structured call decides how to route the user's message, and (where
relevant) extracts the document it names, the change it requests, or a time
reference — so a single LLM call covers classification + extraction, instead
of a second round-trip per category.
"""

from __future__ import annotations

from app.llm import client as llm
from app.models.ask import ScopeClassification

_SYSTEM_PROMPT = (
    "You route messages for a legal-contract-compliance assistant scoped to vendor "
    "Data Processing Agreements under India's DPDP Act (primary) and GDPR (secondary). "
    "Classify the user's message into exactly one scope:\n"
    "  CONTRACT_QUESTION - asks what a contract (or contracts) actually says, e.g. "
    "'what's our liability cap', 'which vendors allow arbitration in the EU', "
    "'what does DPDP Section 9 require'.\n"
    "  COMPLIANCE_STATUS_QUESTION - asks about what the system itself has done: "
    "findings Detect raised, redlines Suggest drafted, edits that were approved/"
    "fixed/rejected, e.g. 'what issues were found in the NovaHealth MSA', "
    "'what have we fixed this month', 'what was suggested for the liability clause'.\n"
    "  EDIT_INSTRUCTION - asks for an actual change to a named document, e.g. "
    "'edit the Acme MSA to change the liability cap to 2 crore'.\n"
    "  GENERAL_LEGAL_TECH_QUESTION - general legal-tech / regulatory knowledge NOT "
    "tied to the tenant's own documents, e.g. 'what is the DPDP Act', 'what's a "
    "typical liability cap in a vendor DPA', 'what counts as a data fiduciary'.\n"
    "  OUT_OF_SCOPE - unrelated to contracts, compliance, or legal tech at all "
    "(weather, sports, general chit-chat, coding help, etc).\n\n"
    "If the message names a specific document, extract it verbatim into "
    "mentioned_document_name (else leave null) and set document_scope='single'; "
    "otherwise document_scope='portfolio'. If the scope is EDIT_INSTRUCTION, extract "
    "the requested change into requested_change. If the scope is "
    "COMPLIANCE_STATUS_QUESTION and a time period is mentioned (e.g. 'last week', "
    "'since September 1st', 'this month'), extract it verbatim into time_reference, "
    "else leave it null."
)


async def classify_scope(message: str) -> ScopeClassification:
    return await llm.generate_structured(
        prompt=f"USER MESSAGE:\n{message}\n\nClassify it.",
        schema=ScopeClassification,
        system_prompt=_SYSTEM_PROMPT,
    )
