"""Multi-hop traversal + compliance check → severity-scored findings.

For every clause of a contract:
  1. resolve its *effective* meaning by walking OVERRIDES up to 3 hops
  2. NLI-classify the effective text against every relevant PlaybookRule and
     every relevant RegulationClause (ENTAILS / CONTRADICTS / NEUTRAL)
  3. turn CONTRADICTS (and clearly-relevant NEUTRAL gaps) into Findings
  4. additionally flag any buried cross-document override of a liability clause
  5. persist Findings + VIOLATES / CONTRADICTS edges
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.llm import client as llm
from app.models.clause import (
    ClauseType,
    ConfidenceLevel,
    ExtractedClause,
    Finding,
    NLILabel,
    NLIResult,
    Severity,
)

logger = logging.getLogger("pactscan.detect.agent")

# --- which rules / regulations are relevant to which clause type ----------
_LIABILITY = ClauseType.LIMITATION_OF_LIABILITY
_DP = ClauseType.DATA_PROCESSING

RELEVANT_PLAYBOOK: dict[ClauseType, list[str]] = {
    ClauseType.LIMITATION_OF_LIABILITY: ["pb_liability_cap_data_breach"],
    ClauseType.INDEMNIFICATION: ["pb_liability_cap_data_breach"],
    ClauseType.BREACH_NOTIFICATION: ["pb_breach_notification_window"],
    ClauseType.DATA_PROCESSING: [
        "pb_mandatory_dpa_fields",
        "pb_verifiable_parental_consent",
    ],
    ClauseType.CONFIDENTIALITY: ["pb_verifiable_parental_consent"],
    ClauseType.SUBPROCESSOR_OBLIGATIONS: ["pb_subprocessor_approval"],
    ClauseType.DATA_LOCALIZATION_CROSS_BORDER_TRANSFER: ["pb_data_localization_transfer"],
    ClauseType.TERMINATION: ["pb_deletion_return_on_termination"],
    ClauseType.TERMINATION_FOR_CONVENIENCE: ["pb_deletion_return_on_termination"],
    ClauseType.AUDIT_RIGHTS: ["pb_audit_rights"],
}

RELEVANT_REGULATION: dict[ClauseType, list[str]] = {
    ClauseType.DATA_PROCESSING: ["dpdp_s9", "dpdp_s4", "dpdp_s8", "gdpr_art8", "gdpr_art6"],
    ClauseType.CONFIDENTIALITY: ["dpdp_s9", "gdpr_art8"],
    ClauseType.BREACH_NOTIFICATION: ["dpdp_s8"],
    ClauseType.SUBPROCESSOR_OBLIGATIONS: ["dpdp_s8"],
    ClauseType.DATA_LOCALIZATION_CROSS_BORDER_TRANSFER: ["dpdp_s8"],
}

_NLI_SYSTEM_PROMPT = (
    "You perform natural-language inference for contract compliance. Given a contract "
    "clause (its effective text, which may already incorporate later overriding "
    "provisions) and a single rule or regulatory requirement, decide whether the clause "
    "ENTAILS the requirement (clearly satisfies it), CONTRADICTS it (violates or is "
    "incompatible with it), or is NEUTRAL (does not address it). A clause that is vague or "
    "silent on a specific mandatory protection (for example children's data / verifiable "
    "parental consent) where that protection is clearly required CONTRADICTS the "
    "requirement rather than being NEUTRAL, because the agreement would permit "
    "non-compliant processing."
)


def _finding_id(contract_id: str, clause_id: str, rule_id: str) -> str:
    h = hashlib.sha1(f"{contract_id}|{clause_id}|{rule_id}".encode()).hexdigest()
    return f"fnd_{h[:12]}"


async def _classify(effective_text: str, requirement_text: str) -> NLIResult:
    prompt = (
        f"CLAUSE (effective text):\n{effective_text}\n\n"
        f"REQUIREMENT:\n{requirement_text}\n\n"
        "Classify the clause against the requirement."
    )
    return await llm.generate_structured(
        prompt=prompt, schema=NLIResult, system_prompt=_NLI_SYSTEM_PROMPT
    )


def _effective_text(clause: ExtractedClause, overriders: list[dict]) -> str:
    if not overriders:
        return clause.raw_text
    parts = [clause.raw_text]
    for o in overriders:
        parts.append(
            f"[MODIFIED by a later provision on page {o['page_number']}"
            + (f" (scope: {o['scope']})" if o.get("scope") else "")
            + f": {o['raw_text']}]"
        )
    return "\n\n".join(parts)


async def run_detect(
    store: GraphStore,
    contract_id: str,
    tenant_id: str = DEMO_TENANT,
) -> list[Finding]:
    clauses = store.get_clauses_for_contract(contract_id, tenant_id=tenant_id)
    playbook = {r["id"]: r for r in store.get_playbook_rules(tenant_id=tenant_id)}
    regulations = {r["id"]: r for r in store.get_regulation_clauses()}

    findings: list[Finding] = []
    edges: list[tuple[str, str, str]] = []

    for clause in clauses:
        overriders = store.get_overriders(clause.clause_id, max_hops=3, tenant_id=tenant_id)
        override_chain = [clause.clause_id] + [o["id"] for o in overriders]
        effective_text = _effective_text(clause, overriders)

        # (4) buried cross-document override of a liability clause
        if overriders and clause.clause_type in (
            ClauseType.LIMITATION_OF_LIABILITY,
            ClauseType.INDEMNIFICATION,
        ):
            pages = sorted({clause.page_number} | {o["page_number"] for o in overriders})
            scopes = ", ".join(sorted({o["scope"] for o in overriders if o.get("scope")}))
            findings.append(
                Finding(
                    finding_id=_finding_id(contract_id, clause.clause_id, "pb_liability_cap_data_breach:override"),
                    clause_id=clause.clause_id,
                    clause_type=clause.clause_type,
                    page_number=clause.page_number,
                    section_header=clause.section_header,
                    severity=Severity.MEDIUM,
                    rule_or_regulation_violated="Playbook: pb_liability_cap_data_breach (buried cross-document liability change)",
                    explanation=(
                        f"The liability cap in this clause (page {clause.page_number}) is "
                        f"silently modified by a later provision on page "
                        f"{', '.join(str(p) for p in pages if p != clause.page_number)}"
                        + (f" for {scopes}" if scopes else "")
                        + ". A cross-document change to the data-breach liability cap must be "
                        "explicit and conspicuous, not buried in an SOW addendum or schedule."
                    ),
                    confidence=ConfidenceLevel.high,
                    override_chain=override_chain,
                )
            )

        # (2)(3) NLI against relevant playbook rules
        for rule_id in RELEVANT_PLAYBOOK.get(clause.clause_type, []):
            rule = playbook.get(rule_id)
            if not rule:
                continue
            nli = await _classify(effective_text, rule["rule_text"])
            f = _maybe_finding(
                contract_id, clause, override_chain, nli, rule_id,
                f"Playbook: {rule_id}", kind="playbook",
            )
            if f:
                findings.append(f)
                edges.append((clause.clause_id, "CONTRADICTS", rule_id))

        # (2)(3) NLI against relevant regulation clauses
        for reg_id in RELEVANT_REGULATION.get(clause.clause_type, []):
            reg = regulations.get(reg_id)
            if not reg:
                continue
            nli = await _classify(effective_text, reg["text"])
            label = f"{reg['regulation_name']} {reg['section']}"
            f = _maybe_finding(
                contract_id, clause, override_chain, nli, reg_id, label, kind="regulation"
            )
            if f:
                findings.append(f)
                edges.append((clause.clause_id, "VIOLATES", reg_id))

    # de-dup by finding_id (a clause could hit the same rule twice via aliasing)
    unique: dict[str, Finding] = {}
    for f in findings:
        unique.setdefault(f.finding_id, f)
    result = list(unique.values())

    store.replace_findings(contract_id, result, tenant_id=tenant_id)
    store.write_compliance_edges(contract_id, edges, tenant_id=tenant_id)
    store.record_detect_run(
        contract_id, datetime.now(timezone.utc).isoformat(), tenant_id=tenant_id
    )
    logger.info("Detect produced %d findings for %s", len(result), contract_id)
    return result


def _maybe_finding(
    contract_id: str,
    clause: ExtractedClause,
    override_chain: list[str],
    nli: NLIResult,
    rule_id: str,
    rule_label: str,
    kind: str,
) -> Finding | None:
    if nli.label == NLILabel.ENTAILS:
        return None

    if nli.label == NLILabel.CONTRADICTS:
        severity = Severity.HIGH if kind == "regulation" else Severity.MEDIUM
    else:  # NEUTRAL — only a finding when the requirement is clearly relevant
        if nli.confidence != ConfidenceLevel.high:
            return None
        severity = Severity.MEDIUM if kind == "regulation" else Severity.LOW

    return Finding(
        finding_id=_finding_id(contract_id, clause.clause_id, rule_id),
        clause_id=clause.clause_id,
        clause_type=clause.clause_type,
        page_number=clause.page_number,
        section_header=clause.section_header,
        severity=severity,
        rule_or_regulation_violated=rule_label,
        explanation=nli.explanation,
        confidence=nli.confidence,
        override_chain=override_chain if len(override_chain) > 1 else [],
    )
