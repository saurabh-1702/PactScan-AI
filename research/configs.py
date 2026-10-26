"""Script 3 — the checker set-ups compared in the paper.

A "family" is one way of ASKING the model (which prompt, which requirements a
clause is checked against, whether the clause is read together with whatever
overrides it). Each family is run once; its raw verdicts are saved.

A "config" is a family plus a way of TURNING verdicts into findings. Because
that second step is pure post-processing, several configs share one run of
model calls:

  A        original (Phase 1, commit 9bbc499): the original prompt, which tells
           the model that silence on a mandatory protection CONTRADICTS; broad
           routing; clause-level findings
  B        A + the conservative prompt (silence = NEUTRAL)        [Known Issues §10.13]
  C        B + subject routing (a rule is checked only against clauses on its subject)
  D        C + contract-level findings (the full method)          [Known Issues §14.15]
  D_noET   D without reading clauses together with their overrides (ablation)
  P        PactScan as deployed: the app's own run_detect(), unmodified

Held constant across A–D: one batched call per clause (introduced in v2,
Known Issues §10.9), the same client, temperature and model.
"""

from __future__ import annotations

from app.llm import client as llm
from app.models.clause import BatchNLIResult, NLILabel

# --------------------------------------------------------------------------- #
# The original (v1) prompt and routing — verbatim from commit 9bbc499,
# backend/app/agents/detect/detect_agent.py
# --------------------------------------------------------------------------- #
V1_SYSTEM_PROMPT = (
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

BROAD_ROUTING: dict[str, list[str]] = {
    "LIMITATION_OF_LIABILITY": ["pb_liability_cap_data_breach"],
    "INDEMNIFICATION": ["pb_liability_cap_data_breach"],
    "BREACH_NOTIFICATION": ["pb_breach_notification_window", "dpdp_s8"],
    "DATA_PROCESSING": [
        "pb_mandatory_dpa_fields", "pb_verifiable_parental_consent",
        "dpdp_s9", "dpdp_s4", "dpdp_s8", "gdpr_art8", "gdpr_art6",
    ],
    "CONFIDENTIALITY": ["pb_verifiable_parental_consent", "dpdp_s9", "gdpr_art8"],
    "SUBPROCESSOR_OBLIGATIONS": ["pb_subprocessor_approval", "dpdp_s8"],
    "DATA_LOCALIZATION_CROSS_BORDER_TRANSFER": ["pb_data_localization_transfer", "dpdp_s8"],
    "TERMINATION": ["pb_deletion_return_on_termination"],
    "TERMINATION_FOR_CONVENIENCE": ["pb_deletion_return_on_termination"],
    "AUDIT_RIGHTS": ["pb_audit_rights"],
}


def subject_routing(benchmark: dict) -> dict[str, list[str]]:
    """Each requirement is checked only against clauses of its own subject's type."""
    clause_type_of_topic = {t: meta["clause_type"] for t, meta in benchmark["topics"].items()}
    routing: dict[str, list[str]] = {}
    for r in benchmark["requirements"]:
        routing.setdefault(clause_type_of_topic[r["topic"]], []).append(r["id"])
    return routing


FAMILIES: dict[str, dict] = {
    "A_original": {"prompt": "v1", "routing": "broad", "effective_text": True},
    "B_prompt": {"prompt": "v3", "routing": "broad", "effective_text": True},
    "C_routing": {"prompt": "v3", "routing": "subject", "effective_text": True},
    "C_noET": {"prompt": "v3", "routing": "subject", "effective_text": False},
}

CONFIGS: dict[str, dict] = {
    "A": {"family": "A_original", "rule": "clause", "name": "Original (v1)"},
    "B": {"family": "B_prompt", "rule": "clause", "name": "+ conservative prompt"},
    "C": {"family": "C_routing", "rule": "clause", "name": "+ subject routing"},
    "D": {"family": "C_routing", "rule": "contract", "name": "+ contract-level findings (full)"},
    "D_noET": {"family": "C_noET", "rule": "contract", "name": "full, without override-aware reading"},
    "P": {"family": None, "rule": "deployed", "name": "PactScan as deployed"},
}


def routing_for(family: dict, benchmark: dict) -> dict[str, list[str]]:
    return BROAD_ROUTING if family["routing"] == "broad" else subject_routing(benchmark)


async def classify(family: dict, effective_text: str, requirements: list[tuple[str, str, str, str]]) -> BatchNLIResult:
    """One batched call: a clause against every requirement routed to it."""
    if family["prompt"] == "v3":
        from app.agents.detect.detect_agent import _classify_batch

        return await _classify_batch(effective_text, requirements)
    # v1 system prompt, same batched request body as the app's _classify_batch
    lines = "\n".join(f"- requirement_id={req_id!r}: {text}" for req_id, _k, _l, text in requirements)
    prompt = (
        f"CLAUSE (effective text):\n{effective_text}\n\n"
        f"REQUIREMENTS:\n{lines}\n\n"
        "Classify the clause against each requirement."
    )
    return await llm.generate_structured(prompt=prompt, schema=BatchNLIResult, system_prompt=V1_SYSTEM_PROMPT)


# --------------------------------------------------------------------------- #
# Turning verdicts into findings
# --------------------------------------------------------------------------- #
def clause_rule(verdicts: list[dict]) -> int:
    """The original Phase 1 rule (``_maybe_finding`` in 9bbc499): a CONTRADICTS
    is a finding; a NEUTRAL with high confidence is also a finding ("clearly
    relevant gap"). Returns the number of findings for this requirement."""
    return sum(
        1 for v in verdicts
        if v["label"] == NLILabel.CONTRADICTS.value
        or (v["label"] == NLILabel.NEUTRAL.value and v.get("confidence") == "high")
    )


def contract_rule(verdicts: list[dict], mandatory: bool) -> int:
    """The full method: one decision per (contract, requirement).
    any CONTRADICTS -> one finding per contradicting clause;
    else any ENTAILS -> nothing (the contract covers it somewhere);
    else (silent everywhere, or no clause on the subject at all) -> ONE gap
    finding if the requirement is mandatory, otherwise nothing."""
    contradicts = sum(1 for v in verdicts if v["label"] == NLILabel.CONTRADICTS.value)
    if contradicts:
        return contradicts
    if any(v["label"] == NLILabel.ENTAILS.value for v in verdicts):
        return 0
    return 1 if mandatory else 0
