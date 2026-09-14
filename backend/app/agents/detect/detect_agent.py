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
    BatchNLIItem,
    BatchNLIResult,
    ClauseType,
    ConfidenceLevel,
    ExtractedClause,
    Finding,
    NLILabel,
    NLIResult,
    Severity,
)

logger = logging.getLogger("pactscan.detect.agent")

# A clause type is only NLI-checked against the rules / regulations that plausibly
# govern that exact subject. Deliberately narrow — checking every data-processing
# clause against every regulation makes a real LLM over-flag "this clause doesn't
# ALSO restate obligation X".
_LIABILITY_TYPES = (ClauseType.LIMITATION_OF_LIABILITY, ClauseType.INDEMNIFICATION)
RELEVANT_PLAYBOOK: dict[ClauseType, list[str]] = {
    ClauseType.LIMITATION_OF_LIABILITY: ["pb_liability_cap_data_breach"],
    ClauseType.INDEMNIFICATION: ["pb_liability_cap_data_breach"],
    ClauseType.BREACH_NOTIFICATION: ["pb_breach_notification_window"],
    ClauseType.DATA_PROCESSING: ["pb_verifiable_parental_consent"],
    ClauseType.CONFIDENTIALITY: ["pb_verifiable_parental_consent"],
    ClauseType.SUBPROCESSOR_OBLIGATIONS: ["pb_subprocessor_approval"],
    ClauseType.DATA_LOCALIZATION_CROSS_BORDER_TRANSFER: ["pb_data_localization_transfer"],
    ClauseType.TERMINATION: ["pb_deletion_return_on_termination"],
    ClauseType.TERMINATION_FOR_CONVENIENCE: ["pb_deletion_return_on_termination"],
    ClauseType.AUDIT_RIGHTS: ["pb_audit_rights"],
}

RELEVANT_REGULATION: dict[ClauseType, list[str]] = {
    ClauseType.DATA_PROCESSING: ["dpdp_s9", "gdpr_art8"],
    ClauseType.CONFIDENTIALITY: ["dpdp_s9", "gdpr_art8"],
    ClauseType.BREACH_NOTIFICATION: ["dpdp_s8"],
}

# NEUTRAL (clause is silent) becomes a finding ONLY for these requirements, and
# ONLY when no clause anywhere in the contract ENTAILS them — i.e. a mandatory
# protection the whole agreement omits. Every other NEUTRAL is just "not relevant
# to this clause" and produces nothing.
_MANDATORY_GAP_REQS = {"dpdp_s9", "gdpr_art8"}

_NLI_SYSTEM_PROMPT = (
    "You perform natural-language inference for contract-compliance review. You are "
    "given ONE contract clause (its effective text, which may already incorporate "
    "later overriding provisions) and a list of requirements. Classify the clause "
    "against EACH requirement independently:\n"
    "  ENTAILS     - the clause affirmatively satisfies this requirement\n"
    "  CONTRADICTS - the clause affirmatively permits or requires something this "
    "requirement forbids, OR it governs exactly this requirement's subject but omits "
    "a protection the requirement makes mandatory\n"
    "  NEUTRAL     - the clause simply does not deal with this requirement's subject\n"
    "Be conservative. A clause that is about a different topic, or that is merely "
    "silent on an adjacent obligation, is NEUTRAL — not CONTRADICTS. Only use "
    "CONTRADICTS when the clause itself creates the compliance problem. Return exactly "
    "one result per requirement, echoing back its requirement_id."
)


def finding_id(contract_id: str, clause_id: str, rule_id: str) -> str:
    """Deterministic/idempotent finding id — exported so Horizon-Scanning
    (app/agents/horizon_scanning/rediff.py) mints ids the same way Detect
    does, keeping the two finding sources indistinguishable in storage."""
    h = hashlib.sha1(f"{contract_id}|{clause_id}|{rule_id}".encode()).hexdigest()
    return f"fnd_{h[:12]}"


async def _classify_batch(
    effective_text: str, requirements: list[tuple[str, str, str, str]]
) -> BatchNLIResult:
    """One structured call classifying the clause against every relevant
    requirement (id, kind, label, text)."""
    lines = "\n".join(
        f"- requirement_id={req_id!r}: {text}" for req_id, _kind, _label, text in requirements
    )
    prompt = (
        f"CLAUSE (effective text):\n{effective_text}\n\n"
        f"REQUIREMENTS:\n{lines}\n\n"
        "Classify the clause against each requirement."
    )
    return await llm.generate_structured(
        prompt=prompt, schema=BatchNLIResult, system_prompt=_NLI_SYSTEM_PROMPT
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
    # per-requirement NLI verdicts across the whole contract, for cross-clause logic
    verdicts_by_req: dict[str, list[NLILabel]] = {}
    # (clause, req_id, kind, label, item, override_chain) for NEUTRAL gaps deferred to pass 2
    deferred_gaps: list[tuple] = []

    for clause in clauses:
        overriders = store.get_overriders(clause.clause_id, max_hops=3, tenant_id=tenant_id)
        override_chain = [clause.clause_id] + [o["id"] for o in overriders]
        effective_text = _effective_text(clause, overriders)

        # (4) buried cross-document override of a liability clause — deterministic
        if overriders and clause.clause_type in _LIABILITY_TYPES:
            pages = sorted({clause.page_number} | {o["page_number"] for o in overriders})
            scopes = ", ".join(sorted({o["scope"] for o in overriders if o.get("scope")}))
            findings.append(
                Finding(
                    finding_id=finding_id(contract_id, clause.clause_id, "pb_liability_cap_data_breach:override"),
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

        # (2)(3) NLI against every relevant playbook rule + regulation, in ONE call
        requirements: list[tuple[str, str, str, str]] = []
        for rule_id in RELEVANT_PLAYBOOK.get(clause.clause_type, []):
            rule = playbook.get(rule_id)
            if rule:
                requirements.append(
                    (rule_id, "playbook", f"Playbook: {rule_id}", rule["rule_text"])
                )
        for reg_id in RELEVANT_REGULATION.get(clause.clause_type, []):
            reg = regulations.get(reg_id)
            if reg:
                requirements.append(
                    (reg_id, "regulation", f"{reg['regulation_name']} {reg['section']}", reg["text"])
                )
        if not requirements:
            continue

        batch = await _classify_batch(effective_text, requirements)
        by_id = {item.requirement_id: item for item in batch.results}
        for req_id, kind, label, _text in requirements:
            item = by_id.get(req_id)
            if item is None:
                continue
            verdicts_by_req.setdefault(req_id, []).append(item.label)

            if item.label == NLILabel.CONTRADICTS:
                findings.append(
                    build_finding_from_nli(contract_id, clause, override_chain, item, req_id, label, kind)
                )
                edges.append(
                    (clause.clause_id, "VIOLATES" if kind == "regulation" else "CONTRADICTS", req_id)
                )
            elif item.label == NLILabel.NEUTRAL and req_id in _MANDATORY_GAP_REQS:
                deferred_gaps.append(
                    (clause, req_id, kind, label, item, override_chain)
                )

    # pass 2 — a NEUTRAL on a mandatory-protection requirement is a finding only if
    # NOTHING in the whole contract ENTAILS that requirement
    seen_gap_reqs: set[str] = set()
    for clause, req_id, kind, label, item, override_chain in deferred_gaps:
        verdicts = verdicts_by_req.get(req_id, [])
        if NLILabel.ENTAILS in verdicts or NLILabel.CONTRADICTS in verdicts:
            continue  # already covered, or already flagged elsewhere
        if req_id in seen_gap_reqs:
            continue
        seen_gap_reqs.add(req_id)
        severity = Severity.HIGH if kind == "regulation" else Severity.MEDIUM
        findings.append(
            Finding(
                finding_id=finding_id(contract_id, clause.clause_id, req_id),
                clause_id=clause.clause_id,
                clause_type=clause.clause_type,
                page_number=clause.page_number,
                section_header=clause.section_header,
                severity=severity,
                rule_or_regulation_violated=label,
                explanation=(
                    f"No clause in this contract addresses the requirement: {item.explanation}"
                ),
                confidence=item.confidence,
                override_chain=override_chain if len(override_chain) > 1 else [],
            )
        )
        edges.append(
            (clause.clause_id, "VIOLATES" if kind == "regulation" else "CONTRADICTS", req_id)
        )

    # de-dup by finding_id
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


def build_finding_from_nli(
    contract_id: str,
    clause: ExtractedClause,
    override_chain: list[str],
    nli: NLIResult | BatchNLIItem,
    rule_id: str,
    rule_label: str,
    kind: str,
) -> Finding:
    severity = Severity.HIGH if kind == "regulation" else Severity.MEDIUM
    return Finding(
        finding_id=finding_id(contract_id, clause.clause_id, rule_id),
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
