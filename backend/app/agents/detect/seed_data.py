"""Seed the compliance playbook and both regulations into the graph.

Idempotent (MERGE-based). Called from the FastAPI startup lifespan event.

Scope: vendor DPA / data-processing concerns only — not generic contract law.
DPDP (India) is the primary regulation; GDPR is secondary, retained to
demonstrate the same taxonomy generalises to a second jurisdiction.
"""

from __future__ import annotations

import logging

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.models.clause import ClauseType

logger = logging.getLogger("pactscan.detect.seed")

# --- Playbook: 8 vendor-DPA rules ------------------------------------------
PLAYBOOK_RULES: list[dict] = [
    {
        "id": "pb_breach_notification_window",
        "category": ClauseType.BREACH_NOTIFICATION.value,
        "rule_text": (
            "The vendor must notify the company of any personal-data breach without undue "
            "delay and in any case within 72 hours of becoming aware of it."
        ),
    },
    {
        "id": "pb_liability_cap_data_breach",
        "category": ClauseType.LIMITATION_OF_LIABILITY.value,
        "rule_text": (
            "Liability for data-breach and confidentiality events must not be capped below "
            "the greater of 12 months' fees or a negotiated data-incident floor, and any "
            "cross-document change to that cap must be explicit and conspicuous, not buried "
            "in a schedule or SOW addendum."
        ),
    },
    {
        "id": "pb_mandatory_dpa_fields",
        "category": ClauseType.DATA_PROCESSING.value,
        "rule_text": (
            "The DPA must specify the purpose of processing, the categories of personal data "
            "and data principals, and the retention period for each category."
        ),
    },
    {
        "id": "pb_verifiable_parental_consent",
        "category": ClauseType.DATA_PROCESSING.value,
        "rule_text": (
            "Where children's or minors' personal data may be processed, the agreement must "
            "require verifiable parental / lawful-guardian consent before such processing and "
            "prohibit behavioural tracking or targeted advertising directed at children."
        ),
    },
    {
        "id": "pb_subprocessor_approval",
        "category": ClauseType.SUBPROCESSOR_OBLIGATIONS.value,
        "rule_text": (
            "The vendor must obtain the company's prior written approval before engaging any "
            "sub-processor and must flow down equivalent data-protection obligations."
        ),
    },
    {
        "id": "pb_data_localization_transfer",
        "category": ClauseType.DATA_LOCALIZATION_CROSS_BORDER_TRANSFER.value,
        "rule_text": (
            "Cross-border transfer of personal data is permitted only to jurisdictions not "
            "restricted by the Central Government and subject to appropriate safeguards; "
            "the agreement must identify the storage and processing locations."
        ),
    },
    {
        "id": "pb_deletion_return_on_termination",
        "category": ClauseType.TERMINATION.value,
        "rule_text": (
            "On termination or expiry the vendor must, at the company's choice, delete or "
            "return all personal data and certify deletion within 30 days."
        ),
    },
    {
        "id": "pb_audit_rights",
        "category": ClauseType.AUDIT_RIGHTS.value,
        "rule_text": (
            "The company must have the right to audit the vendor's data-processing practices, "
            "directly or via an independent auditor, at least annually and after any breach."
        ),
    },
]

# --- DPDP (India) — primary regulation: 3 clauses -------------------------
DPDP_CLAUSES: list[dict] = [
    {
        "id": "dpdp_s9",
        "regulation_name": "DPDP Act 2023 (India)",
        "section": "Section 9",
        "text": (
            "Section 9 — Processing of personal data of children: a Data Fiduciary must obtain "
            "verifiable consent of a parent or lawful guardian before processing any personal "
            "data of a child, and must not undertake tracking, behavioural monitoring, or "
            "targeted advertising directed at children."
        ),
    },
    {
        "id": "dpdp_s4",
        "regulation_name": "DPDP Act 2023 (India)",
        "section": "Section 4",
        "text": (
            "Section 4 — Grounds for processing personal data: personal data may be processed "
            "only for a lawful purpose for which the Data Principal has given consent, or for "
            "certain legitimate uses. Consent must be free, specific, informed, unconditional "
            "and unambiguous, with a clear affirmative action."
        ),
    },
    {
        "id": "dpdp_s8",
        "regulation_name": "DPDP Act 2023 (India)",
        "section": "Section 8",
        "text": (
            "Section 8 — General obligations of a Data Fiduciary: implement appropriate "
            "technical and organisational measures, maintain data accuracy, and in the event "
            "of a personal-data breach give the Board and each affected Data Principal notice "
            "in such form and manner as prescribed, without undue delay."
        ),
    },
]

# --- GDPR — secondary regulation: 2 clauses -------------------------------
GDPR_CLAUSES: list[dict] = [
    {
        "id": "gdpr_art8",
        "regulation_name": "GDPR (EU)",
        "section": "Article 8",
        "text": (
            "Article 8 — Conditions applicable to child's consent in relation to information "
            "society services: where consent is the basis, processing of a child's personal "
            "data is lawful only if the child is at least 16 (or the Member State's lower age, "
            "not below 13); otherwise consent must be given or authorised by the holder of "
            "parental responsibility, and the controller must make reasonable efforts to verify it."
        ),
    },
    {
        "id": "gdpr_art6",
        "regulation_name": "GDPR (EU)",
        "section": "Article 6",
        "text": (
            "Article 6 — Lawfulness of processing: processing is lawful only if and to the "
            "extent that at least one legal basis applies (consent, contract, legal obligation, "
            "vital interests, public task, or legitimate interests)."
        ),
    },
]


def seed(store: GraphStore, tenant_id: str = DEMO_TENANT) -> None:
    store.seed_playbook_rules(PLAYBOOK_RULES, tenant_id=tenant_id)
    store.seed_regulation_clauses(DPDP_CLAUSES + GDPR_CLAUSES)
    logger.info(
        "Seeded %d playbook rules, %d DPDP + %d GDPR regulation clauses",
        len(PLAYBOOK_RULES),
        len(DPDP_CLAUSES),
        len(GDPR_CLAUSES),
    )
